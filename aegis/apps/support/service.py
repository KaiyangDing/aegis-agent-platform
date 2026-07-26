"""chat 编排层（M3.8 交付②，plans §4.8）：intent→分支→run 的汇合点。

M3.2 端点收敛调用本层（响应仍 JSON 摘要），M3.10 把帧流式化（ChatFrame 即帧
词汇前身）。分支纪律：
- FAQ 直答守卫（M3.6 后置修订⑴，承重墙）：仅"会话无历史 且 租户配了 faq 摘要"
  才直答——指代上文的跟进问被结构性挡回主 Agent（历史层在场）；
- 直答/直通分支不经过 run：user_message 由本层写（D7），**先答后写**=失败零
  残留、回落主 Agent 不双写；主分支 user_message 由 loop 写（U8），本层绝不碰；
- 兜底路径②：预算类终止 → FALLBACK_LOOP_LIMIT + 建工单 + handoff 事件。
Principal 不进本层：apps 不向上 import api——计划签名的层错已修正（偏差登记）。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from aegis.apps.support.agent import build_agent_spec
from aegis.apps.support.handoff import create_handoff
from aegis.apps.support.intent import Intent, answer_faq, classify
from aegis.apps.support.prompts import FALLBACK_LOOP_LIMIT, HANDOFF_REPLY_TEMPLATE
from aegis.core.locks import SessionLock, hold_session_lock
from aegis.core.tenancy import SessionFactory, TenantDirectory, TenantRecord
from aegis.runtime.events import EventType
from aegis.runtime.runtime import AgentRuntime, GatewayLike
from aegis.runtime.spec import AgentSpec, TerminationReason
from aegis.runtime.store import EventWriter, MessageRecord

logger = logging.getLogger(__name__)

_FALLBACK_REASONS = (TerminationReason.MAX_ITERATIONS.value, TerminationReason.TOKEN_BUDGET_EXCEEDED.value)
"""兜底路径②的触发集（§4.8）：达上限类终止补话术+转人工；其余终止原因原样透出。"""


@dataclass(frozen=True, slots=True)
class ChatFrame:
    """服务层输出帧（M3.10 SSE 帧词汇前身）：kind ∈ token/tool_status/approval_pending/handoff/done。"""

    kind: str
    data: Mapping[str, Any]


@asynccontextmanager
async def _maybe_hold(lock: SessionLock | None, session_id: str) -> AsyncIterator[None]:
    """直答分支的锁语义与 runtime._maybe_lock 同构：None=测试直通（M2.9 拍板）。"""
    if lock is None:
        yield
    else:
        async with hold_session_lock(lock, session_id):
            yield


class ChatService:
    """编排器：不落业务状态（每请求装配 spec）；生产由 create_app 组装（组装在边缘）。"""

    def __init__(
        self,
        *,
        gateway: GatewayLike,
        factory: SessionFactory,
        directory: TenantDirectory,
        runtime: AgentRuntime,
        lock: SessionLock | None = None,
    ) -> None:
        self._gateway = gateway
        self._factory = factory
        self._directory = directory
        self._runtime = runtime
        self._lock = lock

    async def resolve_tenant(self, tenant_id: str) -> TenantRecord:
        """租户行缺失=测试/裸库形态：合成空配置（无工具无 faq）留痕告警、不拒服务——
        JWT 已验签且预算闸门另有兜底；生产种子在位时永不走此支。"""
        tenant = await self._directory.get_tenant(tenant_id)
        if tenant is None:
            logger.warning("租户行缺失，按空配置装配：tenant=%s", tenant_id)
            tenant = TenantRecord(id=tenant_id, name=tenant_id, config={}, token_budget_monthly=0)
        return tenant

    async def build_spec(self, tenant_id: str) -> AgentSpec:
        """端点取消/恢复路径共用的装配口（PLACEHOLDER_SPEC 退役后的替任）。"""
        return build_agent_spec(await self.resolve_tenant(tenant_id))

    async def handle(self, *, tenant_id: str, user_id: str, session_id: str, message: str) -> AsyncIterator[ChatFrame]:
        """一条消息的编排：分类一次 → 三路分支。归属/准入/限流已由端点完成。"""
        tenant = await self.resolve_tenant(tenant_id)
        intent = await classify(self._gateway, message, tenant_id=tenant_id, session_id=session_id)
        faq_digest = str(tenant.config.get("faq") or "")
        if intent is Intent.FAQ and faq_digest and not await self._has_history(session_id):
            async for frame in self._faq_direct(tenant, user_id, session_id, message, faq_digest):
                yield frame
            return
        if intent is Intent.HANDOFF:
            async for frame in self._handoff_direct(tenant, user_id, session_id, message):
                yield frame
            return
        async for frame in self._run_main(tenant, user_id, session_id, message):
            yield frame

    async def _has_history(self, session_id: str) -> bool:
        """守卫判据：messages 投影有行即有历史（FAQ 直答轮也写投影 D7——第二轮起必真）。"""
        async with self._factory() as s:
            n = (
                await s.execute(
                    select(func.count()).select_from(MessageRecord).where(MessageRecord.session_id == session_id)
                )
            ).scalar_one()
        return n > 0

    async def _faq_direct(
        self, tenant: TenantRecord, user_id: str, session_id: str, message: str, faq_digest: str
    ) -> AsyncIterator[ChatFrame]:
        try:
            parts = [
                p
                async for p in answer_faq(
                    self._gateway, message, tenant_id=tenant.id, session_id=session_id, faq_digest=faq_digest
                )
            ]
            text = "".join(parts)
        except Exception:
            # 直答是该轮主路径：失败回落主 Agent（同样正确的路）。先答后写保证此刻
            # 零事件残留——回落后 user_message 由 loop 写，绝不双写
            logger.warning("FAQ 直答失败，回落主 Agent：session=%s", session_id, exc_info=True)
            async for frame in self._run_main(tenant, user_id, session_id, message):
                yield frame
            return
        await self._write_direct(session_id, message, [(EventType.ASSISTANT_MESSAGE, {"content": text})])
        yield ChatFrame("token", {"text": text})
        yield ChatFrame("done", {"reason": "faq_direct", "trace_id": session_id, "events": 2})

    async def _handoff_direct(
        self, tenant: TenantRecord, user_id: str, session_id: str, message: str
    ) -> AsyncIterator[ChatFrame]:
        result = await create_handoff(
            factory=self._factory, session_id=session_id, tenant_id=tenant.id, user_id=user_id, reason="user_requested"
        )
        reply = HANDOFF_REPLY_TEMPLATE.format(ticket_id=result["ticket_id"])
        await self._write_direct(
            session_id,
            message,
            [(EventType.HANDOFF, dict(result)), (EventType.ASSISTANT_MESSAGE, {"content": reply})],
        )
        yield ChatFrame("token", {"text": reply})
        yield ChatFrame("handoff", dict(result))
        yield ChatFrame("done", {"reason": "handoff", "trace_id": session_id, "events": 3})

    async def _write_direct(
        self, session_id: str, user_text: str, tail: list[tuple[EventType, dict[str, Any]]]
    ) -> None:
        """直答/直通分支的事件落盘（D7）：user_message 起头+尾随事件，单写者在锁内。"""
        async with _maybe_hold(self._lock, session_id):
            writer = await EventWriter.open(self._factory, session_id, run_id=uuid4().hex)
            await writer.append(EventType.USER_MESSAGE, {"content": user_text})
            for etype, payload in tail:
                await writer.append(etype, payload)

    async def _run_main(
        self, tenant: TenantRecord, user_id: str, session_id: str, message: str
    ) -> AsyncIterator[ChatFrame]:
        """主分支：RAG/TOOL/AGENT 同入完整 Agent（拍板Ⅲ：检索槽每轮注入，分支不特殊化）。"""
        spec = build_agent_spec(tenant)
        reply: str | None = None
        term: Mapping[str, Any] | None = None
        count = 0
        async for event in self._runtime.run(spec, session_id, message):
            count += 1
            if event.type is EventType.ASSISTANT_MESSAGE:
                reply = str(event.payload["content"])
            elif event.type is EventType.TOOL_CALL:
                yield ChatFrame("tool_status", {"tool_name": event.payload["tool_name"], "status": "running"})
            elif event.type is EventType.APPROVAL_REQUESTED:
                yield ChatFrame(
                    "approval_pending",
                    {
                        "approval_id": event.payload["approval_id"],
                        "tool_name": event.payload["tool_name"],
                        "expires_at": event.payload["expires_at"],
                    },
                )
            elif event.type is EventType.LOOP_TERMINATED:
                term = event.payload
        if term is None:
            return  # 干净挂起（D2 哨兵）：approval_pending 帧已发，awaiting 摘要归端点
        reason = str(term["reason"])
        if reason in _FALLBACK_REASONS:
            # 兜底路径②：FALLBACK 话术**替换** loop 的通用打断话术出帧（原话仍在事件流/
            # 历史里，X4 不丢事实）——用户面只见一条带工单号的最终答复
            result = await create_handoff(
                factory=self._factory, session_id=session_id, tenant_id=tenant.id, user_id=user_id, reason=reason
            )
            async with _maybe_hold(self._lock, session_id):
                writer = await EventWriter.open(self._factory, session_id, run_id=uuid4().hex)
                await writer.append(EventType.HANDOFF, dict(result))
            yield ChatFrame("token", {"text": FALLBACK_LOOP_LIMIT})
            yield ChatFrame("handoff", dict(result))
        elif reply is not None:
            yield ChatFrame("token", {"text": reply})
        yield ChatFrame("done", {"reason": reason, "trace_id": session_id, "events": count})

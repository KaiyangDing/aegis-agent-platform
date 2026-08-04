"""chat 编排层（M3.8 交付②，M3.10② 流式化；plans §4.8/§4.10+14j）：intent→分支→run 汇合点。

M3.10② 帧协议升级：逐 token 帧经 L2 text_sink 缝实时产出（观察者不改变事实——
sink 只作用于通道，事件流照旧）；队列解耦生产与消费——token 在 run 推进（消费者
__anext__ 阻塞）期间入队，单生成器无法边收边吐；**消费者退出（断连）不取消生产者**：
run 是事实生产，观察者离场不中断，msgbuf 持续更新、用户经 GET 通道重连补收
（ADR-007 断线语义）。分支纪律沿 M3.8：FAQ 直答守卫（无历史∧有摘要）/直答直通
不经 run、user_message 由本层写（先答后写）/兜底② FALLBACK 替换打断话术出帧
（流式形态=未经通道的话术押后为 pending、终局裁决）。拍板Ⅳ：直答流式段同过
OutputGuard（02 §2⑨ 出口守卫在通道上生效）；拍板Ⅴ：done.usage 从本 run
llm_result 实测累计（直答轮 usage=null 诚实缺席）。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import redis.asyncio as aioredis
from sqlalchemy import func, select

from aegis.apps.support.agent import build_agent_spec
from aegis.apps.support.handoff import create_handoff
from aegis.apps.support.intent import Intent, answer_faq, classify
from aegis.apps.support.prompts import FALLBACK_LOOP_LIMIT, FALLBACK_LOOP_LIMIT_NO_TICKET, HANDOFF_REPLY_TEMPLATE
from aegis.core.locks import SessionLock, hold_session_lock
from aegis.core.tenancy import SessionFactory, TenantDirectory, TenantRecord
from aegis.runtime.events import EventType
from aegis.runtime.guardrails import SAFE_REPLY, Guardrails, output_audit_payload
from aegis.runtime.runtime import AgentRuntime, GatewayLike
from aegis.runtime.spec import AgentSpec, TerminationReason
from aegis.runtime.store import EventWriter, MessageRecord

logger = logging.getLogger(__name__)

_FALLBACK_REASONS = (TerminationReason.MAX_ITERATIONS.value, TerminationReason.TOKEN_BUDGET_EXCEEDED.value)
"""兜底路径②的触发集（§4.8）：达上限类终止补话术+转人工；其余终止原因原样透出。"""

_MSGBUF_TTL_S = 3600
"""进行中消息缓冲 TTL（§4.10）：Redis 挂/清除失败时的自然过期兜底。"""


def msgbuf_key(session_id: str) -> str:
    """缓冲键单点（ADR-005 角色1）：GET 通道（M3.10③）按同键读，改动两端同源。"""
    return f"aegis:msgbuf:{session_id}"


@dataclass(frozen=True, slots=True)
class ChatFrame:
    """服务层输出帧=SSE 帧词汇（M3.10② 拍板Ⅲ：单一帧类型贯穿 service→通道）：
    kind ∈ token/user_message/tool_status/approval_pending/handoff/done/error/message_reset
    （user_message 仅 GET 回放在场——POST 侧用户消息本地已有，(73)）；
    seq 仅 GET 通道回放事件时在场（编码为 SSE id:，Last-Event-ID 续传）。"""

    kind: str
    data: Mapping[str, Any]
    seq: int | None = None


_BACKGROUND: set[asyncio.Task[None]] = set()
"""脱缰生产者的强引用池（asyncio 纪律：running task 需持引用防 GC）。"""


def _reap_producer(task: asyncio.Task[None]) -> None:
    _BACKGROUND.discard(task)
    if not task.cancelled():
        exc = task.exception()  # 取回即标记 retrieved——压掉"never retrieved"日志噪音
        if exc is not None:
            # 有观察者时该异常已由 handle 尾部 await 重抛给端点；此处低噪留痕即可
            logger.debug("chat 生产者收尾异常（多数已由端点处理）：%r", exc)


class _TokenEmitter:
    """单请求 token 出口（per-request 状态绝不上 ChatService——服务是进程级单例）。

    三职责：帧入队；msgbuf 全量覆盖（**先写缓冲后入帧**——"消费到帧⇒缓冲可见"的
    顺序承诺，测试与 GET 通道都吃它；Redis 挂=本请求降级留痕，绝不拖垮主链路）；
    turn_text 记账（服务层判"assistant_message 是否已流出"的判据，llm_call 清零）。
    """

    def __init__(self, queue: asyncio.Queue[ChatFrame | None], redis: aioredis.Redis | None, session_id: str) -> None:
        self._queue = queue
        self._redis = redis
        self._sid = session_id
        self._acc = ""
        self._down = False
        self.turn_text = ""

    def mark_turn(self) -> None:
        self.turn_text = ""

    async def emit(self, text: str) -> None:
        self.turn_text += text
        self._acc += text
        if self._redis is not None and not self._down:
            try:
                await self._redis.set(msgbuf_key(self._sid), self._acc, ex=_MSGBUF_TTL_S)
            except Exception:
                self._down = True
                logger.warning("msgbuf 写入失败，本请求降级无缓冲：session=%s", self._sid)
        await self._queue.put(ChatFrame("token", {"text": text}))

    async def clear(self) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.delete(msgbuf_key(self._sid))
        except Exception:
            logger.warning("msgbuf 清除失败（TTL %ds 兜底）：session=%s", _MSGBUF_TTL_S, self._sid)


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
        redis: aioredis.Redis | None = None,
    ) -> None:
        self._gateway = gateway
        self._factory = factory
        self._directory = directory
        self._runtime = runtime
        self._lock = lock
        self._redis = redis  # msgbuf 通道（M3.10②）；None=无缓冲（测试形态/降级）

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
        """一条消息的编排：分类一次 → 三路分支；帧经队列实时出流（模块 docstring）。"""
        queue: asyncio.Queue[ChatFrame | None] = asyncio.Queue()
        produced = asyncio.create_task(
            self._produce(queue, tenant_id=tenant_id, user_id=user_id, session_id=session_id, message=message)
        )
        _BACKGROUND.add(produced)
        produced.add_done_callback(_reap_producer)
        while (frame := await queue.get()) is not None:
            yield frame
        await produced  # 生产者异常在此重抛——首帧前的 SessionLockHeld 经端点 peek 仍映射 409

    async def _produce(
        self, queue: asyncio.Queue[ChatFrame | None], *, tenant_id: str, user_id: str, session_id: str, message: str
    ) -> None:
        try:
            tenant = await self.resolve_tenant(tenant_id)
            # M4.7 ㊵：装配前置到 classify 之前——未知工具名等配置错误此前是"花完分诊的
            # 钱再炸成 500 空流"（每请求装配期 ValueError 无人接）；现在花钱之前拦截、
            # 响亮留痕（配置 bug 不是用户错），用户得到可见的 error 帧而非空响应
            try:
                spec = build_agent_spec(tenant)
            except ValueError:
                logger.exception("租户 %s 配置装配失败（配置 bug，fail-loud）：session=%s", tenant_id, session_id)
                await queue.put(ChatFrame("error", {"message": "租户配置错误，请联系管理员处理。"}))
                return
            intent = await classify(self._gateway, message, tenant_id=tenant_id, session_id=session_id)
            faq_digest = str(tenant.config.get("faq") or "")
            if intent is Intent.FAQ and faq_digest:
                if await self._try_faq_direct(queue, spec, tenant, session_id, message, faq_digest):
                    return
                await self._run_main(queue, tenant, user_id, session_id, message, spec)
            elif intent is Intent.HANDOFF:
                await self._handoff_direct(queue, tenant, user_id, session_id, message)
            else:
                await self._run_main(queue, tenant, user_id, session_id, message, spec)
        finally:
            await queue.put(None)  # 哨兵恒发：异常路径消费者才能退出等待、经 await 收到异常

    async def _try_faq_direct(
        self,
        queue: asyncio.Queue[ChatFrame | None],
        spec: AgentSpec,
        tenant: TenantRecord,
        session_id: str,
        message: str,
        faq_digest: str,
    ) -> bool:
        """FAQ 直答的判据与执行整体在会话锁内（M4.7 ㊸㊹）。返回 False=让主循环接手。

        ㊹ `_has_history` 判完到用完之间原有并发窗；㊸ 直答 LLM 流式全程原本无锁——
        并发的主 run 可在流中抢锁，用户看完答案却收 error 帧且答案不入事件流。
        现在判据+流式+写盘同锁段。**回落必须发生在锁释放之后**：runtime 会自取
        同一把会话锁，锁内回落=自撞 SessionLockHeld（M3.2 偏差⑼ 端点不自取锁同族）。
        """
        async with _maybe_hold(self._lock, session_id):
            if await self._has_history(session_id):
                return False
            # M4.4③ ㊴：直答绕过主 Agent，入口规则库原本全程不在场——这里补上
            # （未注入分类器=纯规则库零 LLM）；HIGH 回落主循环，loop 侧完整处置
            # （拒答话术+guardrail_triggered 审计+D10 completed 终止）
            if (await Guardrails().check_input(message)).refuse:
                return False
            return await self._faq_direct(queue, spec, tenant, session_id, message, faq_digest)

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
        self,
        queue: asyncio.Queue[ChatFrame | None],
        spec: AgentSpec,
        tenant: TenantRecord,
        session_id: str,
        message: str,
        faq_digest: str,
    ) -> bool:
        """直答执行体（调用方 `_try_faq_direct` 已持会话锁——本方法不再自取，M4.7 ㊸）。

        返回 True=已完成（含写盘与 done 帧）；False=流失败，调用方在**锁外**回落主循环
        （旧形态在本方法内直接调 _run_main——锁化后那会自撞，回落职责上移）。
        """
        # 拍板Ⅳ：直答是"通道上的出口"，02 §2⑨ 守卫在通道生效——参数与主 Agent 同源
        guard = Guardrails().output_guard(
            system_prompt=spec.system_prompt,
            tool_names=[t.name for t in spec.tools],
            owned_values=spec.owned_values,
        )
        emitter = _TokenEmitter(queue, self._redis, session_id)
        visible = ""
        try:
            async for part in answer_faq(
                self._gateway, message, tenant_id=tenant.id, session_id=session_id, faq_digest=faq_digest
            ):
                released = guard.feed(part)
                if released:
                    visible += released
                    await emitter.emit(released)
            tail = guard.flush()
            if tail:
                visible += tail
                await emitter.emit(tail)
        except Exception:
            # 直答是主路径：失败回落主 Agent（同样正确的路）。先答后写=此刻零事件残留；
            # 已推段作废是通道现实（流式代价），缓冲清掉防 GET 侧残影
            logger.warning("FAQ 直答失败，回落主 Agent：session=%s", session_id, exc_info=True)
            await emitter.clear()
            return False
        hit = guard.hit
        final_hits = [] if hit is not None else guard.final_check(visible)
        tail_events: list[tuple[EventType, dict[str, Any]]]
        if hit is not None or final_hits:
            # 直答通道命中同样留审计（与 loop 挂点③对齐）；流中命中=通道≡事件，
            # 终局命中=事件存 SAFE_REPLY 为准（已推流不可撤回，14j 已知分岔）
            await emitter.emit(SAFE_REPLY)
            stage = "stream" if hit is not None else "final"
            content = (visible + SAFE_REPLY) if hit is not None else SAFE_REPLY
            tail_events = [
                (EventType.GUARDRAIL_TRIGGERED, output_audit_payload(hit or final_hits[0], stage=stage)),
                (EventType.ASSISTANT_MESSAGE, {"content": content, "guardrail_truncated": True}),
            ]
        else:
            tail_events = [(EventType.ASSISTANT_MESSAGE, {"content": visible})]
        await self._append_direct(session_id, message, tail_events)  # 锁已由调用方持有
        await emitter.clear()
        await queue.put(ChatFrame("done", {"reason": "faq_direct", "trace_id": session_id, "usage": None}))
        return True

    async def _handoff_direct(
        self,
        queue: asyncio.Queue[ChatFrame | None],
        tenant: TenantRecord,
        user_id: str,
        session_id: str,
        message: str,
    ) -> None:
        # M4.7 ㊽：带键走 post_write 单点（#43 分界从此覆盖 handoff 写）。键用 uuid4：
        # 直通路径无重试机制（失败=用户重发=合法新单），稳定键在此无消费方
        result = await create_handoff(
            factory=self._factory,
            session_id=session_id,
            tenant_id=tenant.id,
            user_id=user_id,
            reason="user_requested",
            idempotency_key=uuid4().hex,
        )
        reply = HANDOFF_REPLY_TEMPLATE.format(ticket_id=result["ticket_id"])
        await self._write_direct(
            session_id,
            message,
            [(EventType.HANDOFF, dict(result)), (EventType.ASSISTANT_MESSAGE, {"content": reply})],
        )
        await queue.put(ChatFrame("token", {"text": reply}))  # 运行时模板：M2.8 豁免口径不过守卫
        await queue.put(ChatFrame("handoff", dict(result)))
        await queue.put(ChatFrame("done", {"reason": "handoff", "trace_id": session_id, "usage": None}))

    async def _append_direct(
        self, session_id: str, user_text: str, tail: list[tuple[EventType, dict[str, Any]]]
    ) -> None:
        """直答/直通事件落盘核心（D7）：user_message 起头+尾随事件。**不自取锁**——
        锁语义归调用方（_write_direct 包锁；_faq_direct 由 _try_faq_direct 的锁段覆盖）。"""
        writer = await EventWriter.open(self._factory, session_id, run_id=uuid4().hex)
        await writer.append(EventType.USER_MESSAGE, {"content": user_text})
        for etype, payload in tail:
            await writer.append(etype, payload)

    async def _write_direct(
        self, session_id: str, user_text: str, tail: list[tuple[EventType, dict[str, Any]]]
    ) -> None:
        """带锁形态（HANDOFF 直通消费；直答已整段持锁改用 _append_direct——M4.7 ㊸）。"""
        async with _maybe_hold(self._lock, session_id):
            await self._append_direct(session_id, user_text, tail)

    async def _run_main(
        self,
        queue: asyncio.Queue[ChatFrame | None],
        tenant: TenantRecord,
        user_id: str,
        session_id: str,
        message: str,
        spec: AgentSpec,
    ) -> None:
        """主分支：RAG/TOOL/AGENT 同入完整 Agent；逐 token 经 L2 text_sink 缝实时出流。

        帧译规则：llm_call=turn 记账清零（不出帧）；assistant_message 与本 turn 流出
        文本不等=未经通道的话术（打断兜底等）→ 押后 pending、终局裁决后出帧
        （FALLBACK_REASONS 被替换丢弃——M3.8"替换非叠加"定案的流式形态）；
        usage 从 llm_result(ok) 实测累计（拍板Ⅴ）。挂起=无终止事件：清缓冲、
        不发 done（approval_pending 已出帧，客户端据此换 GET 通道——ADR-007）。
        spec 由 _produce 预装配递入（M4.7 ㊵：配置错误在花钱之前拦截）。
        """
        emitter = _TokenEmitter(queue, self._redis, session_id)
        pending: str | None = None
        term: Mapping[str, Any] | None = None
        prompt_tokens = completion_tokens = 0
        last_tool = ""
        async for event in self._runtime.run(spec, session_id, message, text_sink=emitter.emit):
            if event.type is EventType.LLM_CALL:
                emitter.mark_turn()
            elif event.type is EventType.LLM_RESULT and event.payload.get("status") == "ok":
                usage = event.payload.get("usage") or {}
                prompt_tokens += int(usage.get("prompt_tokens") or 0)
                completion_tokens += int(usage.get("completion_tokens") or 0)
            elif event.type is EventType.ASSISTANT_MESSAGE:
                content = str(event.payload["content"])
                if content != emitter.turn_text:
                    pending = content
            elif event.type is EventType.TOOL_CALL:
                last_tool = str(event.payload["tool_name"])
                await queue.put(ChatFrame("tool_status", {"tool_name": last_tool, "status": "running"}))
            elif event.type is EventType.TOOL_RESULT:
                await queue.put(ChatFrame("tool_status", {"tool_name": last_tool, "status": "ok"}))
            elif event.type is EventType.TOOL_ERROR:
                await queue.put(ChatFrame("tool_status", {"tool_name": last_tool, "status": "error"}))
            elif event.type is EventType.APPROVAL_REQUESTED:
                await queue.put(
                    ChatFrame(
                        "approval_pending",
                        {
                            "approval_id": event.payload["approval_id"],
                            "tool_name": event.payload["tool_name"],
                            "expires_at": event.payload["expires_at"],
                        },
                    )
                )
            elif event.type is EventType.LOOP_TERMINATED:
                term = event.payload
        if term is None:
            await emitter.clear()  # 干净挂起：turn 前置残段不留 GET 残影
            return
        reason = str(term["reason"])
        if reason in _FALLBACK_REASONS:
            # 兜底路径②：FALLBACK 话术**替换**打断话术出帧（pending 丢弃；原话在事件流 X4 不丢）
            try:
                result = await create_handoff(
                    factory=self._factory,
                    session_id=session_id,
                    tenant_id=tenant.id,
                    user_id=user_id,
                    reason=reason,
                    idempotency_key=uuid4().hex,
                )
            except Exception:
                # M4.7 ㊻：兜底路径的依赖（mock 后端可用）比主路径**更多**，且失败与
                # "生病"高度相关——建单失败绝不再说"已生成工单"（旧话术把"失败也照发
                # 安抚"这条修法堵死）。改发零承诺话术；事件流已有本 run 的终止与打断
                # 话术（X4 无损失），不补写事件。500 空响应从此不可达。
                logger.exception("兜底建单失败：session=%s reason=%s", session_id, reason)
                await queue.put(ChatFrame("token", {"text": FALLBACK_LOOP_LIMIT_NO_TICKET}))
            else:
                async with _maybe_hold(self._lock, session_id):
                    writer = await EventWriter.open(self._factory, session_id, run_id=uuid4().hex)
                    await writer.append(EventType.HANDOFF, dict(result))
                await queue.put(ChatFrame("token", {"text": FALLBACK_LOOP_LIMIT}))
                await queue.put(ChatFrame("handoff", dict(result)))
        elif pending is not None:
            await queue.put(ChatFrame("token", {"text": pending}))
        await emitter.clear()
        await queue.put(
            ChatFrame(
                "done",
                {
                    "reason": reason,
                    "trace_id": session_id,
                    "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
                },
            )
        )

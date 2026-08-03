"""审批决策 API（M3.9 交付②，plans §4.9 + 14i 拍板Ⅲ——对抗④的机器执行）。

授权序：401 认证 → 403 角色（operator/admin）→ 404 单据不存在 → 403 跨租户
（operator 只裁本租户；admin 平台级放行——02 §7.1 矩阵 ✅ 无限定）→ 409 CAS 输家。
授权查读走 owner 工厂（app.state.approvals_lookup 注入缝）：RLS 下 operator 的
租户上下文看不见他租单，403（存在但无权）与 404（不存在）无法分辨——授权判定
需要平台视角；判定之后的写与恢复回到 tenant_context(单据租户) 内走 app 工厂
（usage admin 特批同款：冒充封闭名单第五处）。
决策=ApprovalStore.decide CAS（C7 fail-closed：过期/已翻转拿 False→409，绝不
覆盖赢家；过期单留 pending 归 reaper）；触发恢复=同步消费 M2.9 恢复单入口
（chat.py 取消路径同形）——handler 绝不自己执行工具，执行在 _resume_locked 的
executor 全程（含 M3.9① precheck 重跑）。崩溃窗（decide 后未消费/消费中途死）
由交付③ #44 分诊支与交付④ 对账扫描兜底。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from aegis.api.auth import Principal, require_roles
from aegis.api.ratelimit import rate_limited
from aegis.apps.support.service import ChatService
from aegis.core.locks import SessionLockHeld
from aegis.core.tenancy import Role, SessionFactory
from aegis.core.tenant_ctx import tenant_context
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.store import (
    ApprovalRecord,
    ApprovalStore,
    EventStoreUnavailable,
    EventWriteFenced,
    LeaseLost,
)

router = APIRouter()


_ADMITTED = rate_limited(require_roles(Role.OPERATOR, Role.ADMIN))
"""M4.2③（观察 (56)）：审批是最花钱的入站入口（一次 POST=一整轮 Agent 续跑），
挂租户维度入站限流——与 chat/kb 同桶（inbound:{tenant_id}）；链序 401→403→429
仍先于一切 handler 逻辑，超限探测不出任何单据存在性。"""


class ApprovalDecision(BaseModel):
    """请求体（§4.9 形状）：二值裁决。撤回是用户动作，走 chat 端点的显式取消，不在此处。"""

    decision: Literal["approve", "reject"]


async def _load_approval(lookup: SessionFactory, approval_id: str) -> ApprovalRecord | None:
    """授权查读（owner 视角）：只读单行，只为 403/404 判定与租户定位服务。"""
    async with lookup() as s:
        return (await s.execute(select(ApprovalRecord).where(ApprovalRecord.id == approval_id))).scalar_one_or_none()


async def _drain(agen: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    """消费恢复事件流；except 阶梯与 chat._collect 同款语义——顺序即语义，详见其 docstring。"""
    try:
        return [event async for event in agen]
    except SessionLockHeld as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="会话正在处理中，请稍后重试") from e
    except (EventStoreUnavailable, EventWriteFenced, LeaseLost):
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="会话状态冲突，请稍后重试") from e


def _summary(approval_id: str, decision: str, session_id: str, events: list[AgentEvent]) -> dict[str, Any]:
    """恢复结果 JSON 摘要（M3.10 换帧）：终止→done；续跑又撞新审批闸→awaiting_approval；
    零事件（T3 输给并发赢家，安静返回）→no_op 空账如实报——旧词 resumed 暗示
    "已续跑成功"，与账（events=0）不符（M4.4③ (57) 措辞修正，词即语义）。"""
    out: dict[str, Any] = {
        "approval_id": approval_id,
        "decision": decision,
        "session_id": session_id,
        "events": len(events),
    }
    term = next((e.payload for e in reversed(events) if e.type is EventType.LOOP_TERMINATED), None)
    reply = next((str(e.payload["content"]) for e in reversed(events) if e.type is EventType.ASSISTANT_MESSAGE), None)
    if term is not None:
        return {**out, "status": "done", "reason": term["reason"], "reply": reply}
    pend = next((e.payload for e in reversed(events) if e.type is EventType.APPROVAL_REQUESTED), None)
    if pend is not None:
        return {
            **out,
            "status": "awaiting_approval",
            "next_approval_id": pend["approval_id"],
            "tool_name": pend["tool_name"],
            "expires_at": pend["expires_at"],
        }
    return {**out, "status": "no_op", "reply": reply}


@router.post("/v1/approvals/{approval_id}")
async def decide_approval(
    approval_id: str,
    body: ApprovalDecision,
    request: Request,
    principal: Annotated[Principal, Depends(_ADMITTED)],
) -> dict[str, Any]:
    factory: SessionFactory = request.app.state.session_factory
    runtime: AgentRuntime = request.app.state.runtime
    service: ChatService | None = request.app.state.chat_service
    lookup: SessionFactory = request.app.state.approvals_lookup
    if service is None:
        # 组装不完整（注入 runtime 却没给 gateway/chat_service）：配置 bug 响亮失败，不降级
        raise RuntimeError("create_app 组装不完整：注入 runtime 时须同时注入 gateway 或 chat_service")
    approval = await _load_approval(lookup, approval_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审批单不存在")
    if principal.role is Role.OPERATOR and principal.tenant_id != approval.tenant_id:
        # 对抗④：跨租户显式 403——staff 端点要的是"越界被点名"，不是 404 隐身
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能裁决其他租户的审批单")
    approved = body.decision == "approve"
    with tenant_context(approval.tenant_id):
        # 判定后以单据租户身份行事（RLS 场内）：decide 的 UPDATE、恢复期读 sessions/
        # approvals、计量落账全在该租户上下文内——operator 本租等值覆盖，admin 跨租特批
        if not await ApprovalStore(factory).decide(approval_id, approved=approved, operator_id=principal.user_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="审批单已失效或已处理")
        spec = await service.build_spec(approval.tenant_id)
        events = await _drain(runtime.resume(spec, approval.session_id, approval_id=approval_id))
    return _summary(approval_id, body.decision, approval.session_id, events)

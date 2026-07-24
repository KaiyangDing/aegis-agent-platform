"""POST /v1/chat 入站前半（M3.2）：认证→角色→限流→归属→准入→驱动 run（02 §2 ①–④）。

占位形态：run 事件全量收集后以 JSON 摘要返回（SSE 化归 M3.10）；AgentSpec 用模块级
占位（无工具无检索，M3.8 按租户装配替换）。user_message 由 loop 写——本层只传原文
进 run，绝不双写（M3.0 实况 #6/U8 定案）。
状态码分工不变量：401 认证 / 403 角色 / 404 归属（不泄露存在性）/ 409 互斥与状态冲突 /
422 载荷 / 429 限流——绝不互相冒充。
取消是安全动作：只认显式 cancel_pending_approval 字段，不做自然语言猜测（plans §4.2）。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from aegis.api.auth import Principal, require_roles
from aegis.api.ratelimit import rate_limited
from aegis.core.locks import SessionLockHeld
from aegis.core.tenancy import Role, SessionFactory
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec
from aegis.runtime.store import (
    ApprovalRecord,
    ApprovalStatus,
    ApprovalStore,
    EventStoreUnavailable,
    EventWriteFenced,
    LeaseLost,
    RunState,
    SessionRecord,
)

router = APIRouter()

PLACEHOLDER_SPEC = AgentSpec(
    system_prompt=(
        "你是云杉电商的客服助手（M3.2 占位形态：无工具、无检索，仅直接回答；"
        "M3.8 起按租户装配替换）。请用中文简洁回答用户问题。"
    )
)
"""M3.6 意图路由与 M3.8 build_agent_spec 落地前的临时注入面——create_app 可整体换掉。"""

_ADMITTED = rate_limited(require_roles(Role.USER, Role.ADMIN))
"""准入链 401→403→429：矩阵 POST /v1/chat 的 operator 列为 —（02 §7.1），坐席不替用户发消息。"""


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")  # 客户端持有，首见即建
    message: str = Field(min_length=1, max_length=4000)
    cancel_pending_approval: bool = False


async def _ensure_session(factory: SessionFactory, session_id: str, principal: Principal) -> str:
    """首见建行（#19 机制：以 JWT 身份落 tenant/user）；归属不符 404 不泄露存在性。返回 run_state。"""
    async with factory() as s:
        row = (await s.execute(select(SessionRecord).where(SessionRecord.id == session_id))).scalar_one_or_none()
    if row is None:
        try:
            async with factory() as s:
                async with s.begin():
                    s.add(SessionRecord(id=session_id, tenant_id=principal.tenant_id, user_id=principal.user_id))
            return RunState.IDLE.value
        except IntegrityError:  # 并发首见撞 PK：别人已建行——回读校归属
            async with factory() as s:
                row = (await s.execute(select(SessionRecord).where(SessionRecord.id == session_id))).scalar_one()
    if row.tenant_id != principal.tenant_id or row.user_id != principal.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return row.run_state


async def _find_pending(factory: SessionFactory, session_id: str) -> ApprovalRecord | None:
    async with factory() as s:
        return (
            await s.execute(
                select(ApprovalRecord).where(
                    ApprovalRecord.session_id == session_id,
                    ApprovalRecord.status == ApprovalStatus.PENDING.value,
                )
            )
        ).scalar_one_or_none()  # 单点挂起不变量：一会话至多一张 pending 单（loop._run_tools）


async def _drain(events_agen: Any) -> list[AgentEvent]:
    """收集 run/resume 事件并把并发信号映射为 409。

    except 阶梯顺序即语义：SessionLockHeld（锁/租约被占）→ 409；事实源三类
    （EventStoreUnavailable/EventWriteFenced/LeaseLost 均为 RuntimeError 子类）
    裸穿=服务不可用级响亮失败；最后才兜 T1 拒绝起跑的裸 RuntimeError（准入读态
    与 run 之间的残余竞态窗）→ 409。顺序错一行就会把围栏自毁吞成客服话术。
    """
    try:
        return [e async for e in events_agen]
    except SessionLockHeld as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="上一条消息处理中") from e
    except (EventStoreUnavailable, EventWriteFenced, LeaseLost):
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="会话状态冲突，请稍后重试") from e


def _summary(session_id: str, events: list[AgentEvent]) -> dict[str, Any]:
    """占位 JSON 摘要（M3.10 换 SSE 帧）：有终止事件 → done；干净挂起（D2 哨兵）→ awaiting_approval。"""
    reply = next((e.payload["content"] for e in reversed(events) if e.type is EventType.ASSISTANT_MESSAGE), None)
    term = next((e.payload for e in reversed(events) if e.type is EventType.LOOP_TERMINATED), None)
    if term is None:  # 无 loop_terminated = 干净挂起，本轮必有 approval_requested
        req = next(e.payload for e in reversed(events) if e.type is EventType.APPROVAL_REQUESTED)
        return {
            "session_id": session_id,
            "status": "awaiting_approval",
            "approval_id": req["approval_id"],
            "tool_name": req["tool_name"],
            "expires_at": req["expires_at"],
        }
    return {
        "session_id": session_id,
        "status": "done",
        "reason": term["reason"],
        "reply": reply,
        "events": len(events),
    }


@router.post("/v1/chat")
async def post_chat(
    request: Request,
    body: ChatRequest,
    principal: Annotated[Principal, Depends(_ADMITTED)],
) -> dict[str, Any]:
    factory: SessionFactory = request.app.state.session_factory
    runtime: AgentRuntime = request.app.state.runtime
    spec: AgentSpec = request.app.state.agent_spec
    run_state = await _ensure_session(factory, body.session_id, principal)

    if body.cancel_pending_approval:
        # 显式取消：审批单 CAS 翻 cancelled → M2.9 恢复单入口的拒绝族路径优雅收尾
        pending = await _find_pending(factory, body.session_id)
        if pending is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前无待审批操作可取消")
        if not await ApprovalStore(factory).cancel(pending.id):
            # 与坐席 decide / reaper 到期赛跑输了：绝不覆盖赢家（C11），按当前实况回
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="审批单已失效或已处理")
        events = await _drain(runtime.resume(spec, body.session_id, approval_id=pending.id))
        return {"session_id": body.session_id, "status": "cancelled", "approval_id": pending.id, "events": len(events)}

    if run_state == RunState.AWAITING_APPROVAL.value:
        # 准入规则（02 §2 ③）：审批期间不开新循环；附单号供前端引导取消/等待
        pending = await _find_pending(factory, body.session_id)
        return {
            "session_id": body.session_id,
            "status": "awaiting_approval",
            "detail": "有待审批操作进行中，请等待审批结果或明确取消",
            "approval_id": pending.id if pending else None,
        }

    # 正常路：驱动一次 run。user_message 由 loop 写入首事件——此处只传原文（实况 #6）
    events = await _drain(runtime.run(spec, body.session_id, body.message))
    return _summary(body.session_id, events)

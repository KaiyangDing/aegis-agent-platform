"""POST /v1/chat（M3.2 入站三件 + M3.8② 收敛调用 ChatService）。

准入链归端点（401 认证/403 角色/404 归属/409 冲突/422 载荷/429 限流——分工
不变量，绝不互相冒充）；意图分诊→分支→run 归 ChatService（apps 层）。
user_message 归属：主分支由 loop 写、直答分支由 service 写——端点永不写事件。
响应仍为 JSON 摘要（SSE 化归 M3.10，届时帧直接透传）。
取消是安全动作：只认显式 cancel_pending_approval 字段，不做自然语言猜测。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from aegis.api.auth import Principal, require_roles
from aegis.api.ratelimit import rate_limited
from aegis.apps.support.service import ChatFrame, ChatService
from aegis.core.locks import SessionLockHeld
from aegis.core.tenancy import Role, SessionFactory
from aegis.runtime.runtime import AgentRuntime
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


async def _collect(agen: Any) -> list[Any]:
    """收集帧/事件流并把并发信号映射为 409（M3.2 原样，泛化到帧）。

    except 阶梯顺序即语义：SessionLockHeld（锁/租约被占）→ 409；事实源三类
    （EventStoreUnavailable/EventWriteFenced/LeaseLost 均为 RuntimeError 子类）
    裸穿=服务不可用级响亮失败；最后才兜 T1 拒绝起跑的裸 RuntimeError（准入读态
    与 run 之间的残余竞态窗）→ 409。顺序错一行就会把围栏自毁吞成客服话术。
    """
    try:
        return [x async for x in agen]
    except SessionLockHeld as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="上一条消息处理中") from e
    except (EventStoreUnavailable, EventWriteFenced, LeaseLost):
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="会话状态冲突，请稍后重试") from e


def _summary(session_id: str, frames: list[ChatFrame]) -> dict[str, Any]:
    """占位 JSON 摘要（M3.10 换 SSE 帧）：有 done 帧 → done；干净挂起 → awaiting_approval。"""
    done = next((f.data for f in reversed(frames) if f.kind == "done"), None)
    if done is None:  # 无 done = 干净挂起，本轮必有 approval_pending 帧
        pend = next(f.data for f in reversed(frames) if f.kind == "approval_pending")
        return {
            "session_id": session_id,
            "status": "awaiting_approval",
            "approval_id": pend["approval_id"],
            "tool_name": pend["tool_name"],
            "expires_at": pend["expires_at"],
        }
    reply = next((f.data["text"] for f in reversed(frames) if f.kind == "token"), None)
    return {
        "session_id": session_id,
        "status": "done",
        "reason": done["reason"],
        "reply": reply,
        "events": done.get("events", 0),
    }


@router.post("/v1/chat")
async def post_chat(
    request: Request,
    body: ChatRequest,
    principal: Annotated[Principal, Depends(_ADMITTED)],
) -> dict[str, Any]:
    factory: SessionFactory = request.app.state.session_factory
    runtime: AgentRuntime = request.app.state.runtime
    service: ChatService | None = request.app.state.chat_service
    if service is None:
        # 组装不完整（注入 runtime 却没给 gateway/chat_service）：配置 bug 响亮失败，不降级
        raise RuntimeError("create_app 组装不完整：注入 runtime 时须同时注入 gateway 或 chat_service")
    run_state = await _ensure_session(factory, body.session_id, principal)

    if body.cancel_pending_approval:
        # 显式取消：审批单 CAS 翻 cancelled → M2.9 恢复单入口的拒绝族路径优雅收尾
        pending = await _find_pending(factory, body.session_id)
        if pending is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前无待审批操作可取消")
        if not await ApprovalStore(factory).cancel(pending.id):
            # 与坐席 decide / reaper 到期赛跑输了：绝不覆盖赢家（C11），按当前实况回
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="审批单已失效或已处理")
        spec = await service.build_spec(principal.tenant_id)  # 按租户装配（PLACEHOLDER_SPEC 已退役）
        events = await _collect(runtime.resume(spec, body.session_id, approval_id=pending.id))
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

    # 正常路：交给编排层（intent→分支→run）。user_message 归属见模块 docstring
    frames = await _collect(
        service.handle(
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            session_id=body.session_id,
            message=body.message,
        )
    )
    return _summary(body.session_id, frames)

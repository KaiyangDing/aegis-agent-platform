"""POST /v1/chat（M3.2 入站 + M3.8 编排 + M3.10② SSE 流式化）。

准入链与状态码分工不变量沿 M3.2（401/403/404/409/422/429——全部发生在流开始
之前，绝不互相冒充）；200 一律 text/event-stream（M3.2 占位 JSON 协议退役）。
主分支 peek 首帧：runtime 内锁/T1 竞态发生在首帧之前，peek 让它们仍映射 409
（M3.2 契约保持）；首帧之后已无法改状态码——异常译为 error 帧收流（打码话术，
不透内部异常文本）。取消与 awaiting 准入以短流回应（同端点同媒体类型不分岔）。
取消是安全动作：只认显式 cancel_pending_approval 字段，不做自然语言猜测。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from aegis.api.auth import Principal, require_roles
from aegis.api.ratelimit import rate_limited
from aegis.api.sse import encode_frame
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

logger = logging.getLogger(__name__)
router = APIRouter()

_ADMITTED = rate_limited(require_roles(Role.USER, Role.ADMIN))
"""准入链 401→403→429：矩阵 POST /v1/chat 的 operator 列为 —（02 §7.1），坐席不替用户发消息。"""

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
"""§4.10 陷阱清单：no-cache 防中间缓存攒帧；X-Accel-Buffering 关反代缓冲（M5.3 部署面镜像）。"""


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
                row = (
                    await s.execute(select(SessionRecord).where(SessionRecord.id == session_id))
                ).scalar_one_or_none()
            if row is None:
                # M4.0③（#46）：RLS 在场时回读**仍被过滤成空**——撞 PK 的行属于他租，
                # 我们永远看不见它。原 `.scalar_one()` 在此抛 NoResultFound → 500，
                # 而 500 vs 200 本身就是存在性 oracle，与本函数 docstring"不泄露存在性"
                # 的声明冲突。根因是时序：本函数写于 M3.2、RLS 上于 M3.3，下面那条
                # `row.tenant_id != principal.tenant_id` 归属判定被 RLS 抢答成了死代码
                # （#46 家族：加一层防线会改变上层代码的可达路径）。
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在") from None
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
    """收集事件流并把并发信号映射为 409（取消路径专用；阶梯顺序即语义——详见原注）。"""
    try:
        return [x async for x in agen]
    except SessionLockHeld as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="上一条消息处理中") from e
    except (EventStoreUnavailable, EventWriteFenced, LeaseLost):
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="会话状态冲突，请稍后重试") from e


def _short_stream(frames: list[ChatFrame]) -> StreamingResponse:
    """取消/准入类动作的短流回应：同端点同媒体类型，客户端解析器不分岔。"""

    async def _gen() -> AsyncIterator[str]:
        for frame in frames:
            yield encode_frame(frame)

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


async def _relay(first: ChatFrame, rest: AsyncIterator[ChatFrame]) -> AsyncIterator[str]:
    """已开流的中继：此后异常无法改状态码，译 error 帧收流（已落盘事件不受影响，
    用户可经 GET 通道重连取回真相）。"""
    try:
        yield encode_frame(first)
        async for frame in rest:
            yield encode_frame(frame)
    except Exception:
        logger.exception("SSE 流中异常——译为 error 帧收流")
        yield encode_frame(ChatFrame("error", {"message": "服务暂时不可用，请稍后重试"}))


@router.post("/v1/chat")
async def post_chat(
    request: Request,
    body: ChatRequest,
    principal: Annotated[Principal, Depends(_ADMITTED)],
) -> StreamingResponse:
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
        await _collect(runtime.resume(spec, body.session_id, approval_id=pending.id))
        return _short_stream(
            [
                ChatFrame(
                    "done",
                    {"reason": "cancelled", "approval_id": pending.id, "trace_id": body.session_id, "usage": None},
                )
            ]
        )

    if run_state == RunState.AWAITING_APPROVAL.value:
        # 准入规则（02 §2 ③）：审批期间不开新循环；附单号供前端引导取消/等待
        pending = await _find_pending(factory, body.session_id)
        frames: list[ChatFrame] = []
        if pending is not None:
            frames.append(
                ChatFrame(
                    "approval_pending",
                    {
                        "approval_id": pending.id,
                        "tool_name": pending.tool_name,
                        "expires_at": pending.expires_at.isoformat(),
                    },
                )
            )
        frames.append(ChatFrame("done", {"reason": "awaiting_approval", "trace_id": body.session_id, "usage": None}))
        return _short_stream(frames)

    # 正常路：交给编排层（intent→分支→run）。peek 首帧：锁/T1 竞态仍映射 409（M3.2 契约）
    stream = service.handle(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        session_id=body.session_id,
        message=body.message,
    )
    try:
        first = await anext(stream)
    except StopAsyncIteration:
        return _short_stream([])  # 理论不可达（任何分支至少一帧）——诚实空流
    except SessionLockHeld as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="上一条消息处理中") from e
    except (EventStoreUnavailable, EventWriteFenced, LeaseLost):
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="会话状态冲突，请稍后重试") from e
    return StreamingResponse(_relay(first, stream), media_type="text/event-stream", headers=_SSE_HEADERS)

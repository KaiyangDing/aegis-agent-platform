"""GET /v1/sessions/{session_id}/stream（M3.10③，ADR-007 重订阅通道）。

断线重连与审批后续跑输出的统一入口：after_seq×Last-Event-ID 双源取 max 续传、
事件译帧每帧带 id:=seq、msgbuf 在场回放后先发 message_reset（半句话整条覆盖）、
活尾由 EventNotifier 唤醒（断连降级 after_seq 轮询——C22）。关流两判据：批内见
loop_terminated；或会话已归 idle/failed 且无增量（FAQ 直答类会话无终止事件）。
矩阵：user 本人（#19 归属 404 不泄露）/admin 平台级；operator 列 —（403）。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from aegis.api.auth import Principal, require_roles
from aegis.api.notify import EventNotifier
from aegis.api.sse import encode_frame
from aegis.apps.support.service import ChatFrame, msgbuf_key
from aegis.core.tenancy import Role, SessionFactory
from aegis.runtime.events import EventType
from aegis.runtime.store import EventRecord, RunState, SessionRecord

logger = logging.getLogger(__name__)
router = APIRouter()

_WAIT_TIMEOUT_S = 25.0
"""活尾单次等待上限：无通知也定期醒来重查（连接活性与降级轮询的公倍口径）。"""

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


async def _ensure_owned(factory: SessionFactory, session_id: str, principal: Principal) -> None:
    async with factory() as s:
        row = (await s.execute(select(SessionRecord).where(SessionRecord.id == session_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    if principal.role is Role.USER and (row.tenant_id != principal.tenant_id or row.user_id != principal.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")  # 不泄露存在性（#19）


def _translate(rows: Sequence[Any], state: dict[str, Any]) -> list[ChatFrame]:
    """事件→帧（与 service._run_main 同一张译表；state 跨批携带工具名/usage 累计/终止位）。"""
    frames: list[ChatFrame] = []
    for row in rows:
        etype, payload, seq = row.type, row.payload, row.seq
        if etype == EventType.ASSISTANT_MESSAGE.value:
            frames.append(ChatFrame("token", {"text": str(payload["content"])}, seq=seq))
        elif etype == EventType.TOOL_CALL.value:
            state["last_tool"] = str(payload.get("tool_name", ""))
            frames.append(ChatFrame("tool_status", {"tool_name": state["last_tool"], "status": "running"}, seq=seq))
        elif etype == EventType.TOOL_RESULT.value:
            frames.append(ChatFrame("tool_status", {"tool_name": state["last_tool"], "status": "ok"}, seq=seq))
        elif etype == EventType.TOOL_ERROR.value:
            frames.append(ChatFrame("tool_status", {"tool_name": state["last_tool"], "status": "error"}, seq=seq))
        elif etype == EventType.APPROVAL_REQUESTED.value:
            frames.append(
                ChatFrame(
                    "approval_pending",
                    {
                        "approval_id": payload["approval_id"],
                        "tool_name": payload["tool_name"],
                        "expires_at": payload["expires_at"],
                    },
                    seq=seq,
                )
            )
        elif etype == EventType.HANDOFF.value:
            frames.append(ChatFrame("handoff", dict(payload), seq=seq))
        elif etype == EventType.LLM_RESULT.value and payload.get("status") == "ok":
            usage = payload.get("usage") or {}
            state["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
            state["completion_tokens"] += int(usage.get("completion_tokens") or 0)
        elif etype == EventType.LOOP_TERMINATED.value:
            frames.append(
                ChatFrame(
                    "done",
                    {
                        "reason": str(payload["reason"]),
                        "trace_id": state["sid"],
                        "usage": {
                            "prompt_tokens": state["prompt_tokens"],
                            "completion_tokens": state["completion_tokens"],
                        },
                    },
                    seq=seq,
                )
            )
            state["terminated"] = True
    return frames


@router.get("/v1/sessions/{session_id}/stream")
async def stream_session(
    session_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(require_roles(Role.USER, Role.ADMIN))],
    after_seq: int = 0,
) -> StreamingResponse:
    factory: SessionFactory = request.app.state.session_factory
    notifier: EventNotifier = request.app.state.notifier
    redis: aioredis.Redis | None = request.app.state.msg_redis
    await _ensure_owned(factory, session_id, principal)
    last_event_id = request.headers.get("last-event-id", "").strip()
    if last_event_id.isdigit():
        after_seq = max(after_seq, int(last_event_id))  # 双源取 max（EventSource 重连自动带头）

    async def _gen() -> AsyncIterator[str]:
        cursor = after_seq
        state: dict[str, Any] = {
            "sid": session_id,
            "last_tool": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "terminated": False,
        }
        first_batch = True
        while True:
            async with factory() as s:
                rows = (
                    await s.execute(
                        select(EventRecord.seq, EventRecord.type, EventRecord.payload)
                        .where(EventRecord.session_id == session_id, EventRecord.seq > cursor)
                        .order_by(EventRecord.seq)
                    )
                ).all()
            for frame in _translate(rows, state):
                yield encode_frame(frame)
            if rows:
                cursor = rows[-1].seq
            if first_batch:
                first_batch = False
                # 回放之后、活尾之前：进行中半句整条重推（ADR-007:33/D11；②的
                # "先写缓冲后入帧"顺序承诺在此兑付）。Redis 挂=跳过留痕不拖流
                if redis is not None:
                    try:
                        buffered = await redis.get(msgbuf_key(session_id))
                    except Exception:
                        buffered = None
                        logger.warning("msgbuf 读取失败，跳过重置帧：session=%s", session_id)
                    if buffered:
                        yield encode_frame(ChatFrame("message_reset", {"text": buffered}))
            if state["terminated"]:
                return  # 主 Agent 会话：终止帧已发，关流
            async with factory() as s:
                run_state = (
                    await s.execute(select(SessionRecord.run_state).where(SessionRecord.id == session_id))
                ).scalar_one_or_none()
            if run_state in (RunState.IDLE.value, RunState.FAILED.value, None):
                if not rows:
                    return  # 直答类/已收尾会话：无终止事件也无增量——关流
                continue  # 刚有增量且已归位：再扫一轮确认无尾巴
            await notifier.wait_for(session_id, timeout_s=_WAIT_TIMEOUT_S)

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)

"""M2.2 交付③：投影同事务派生——纯函数、防重、原子性、payload 契约。"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from aegis.runtime.events import EventType
from aegis.runtime.store import (
    EventRecord,
    EventWriter,
    InvocationStatus,
    MessageRecord,
    ProjectionError,
    SessionRecord,
    ToolInvocationRecord,
)


async def _writer(factory, sid: str) -> EventWriter:
    return await EventWriter.open(factory, sid, "r-1")


async def test_user_message_projects_to_messages(db_session_factory) -> None:
    w = await _writer(db_session_factory, "p-1")
    e = await w.append(EventType.USER_MESSAGE, {"content": "耳机想退款"})
    async with db_session_factory() as s:
        row = (await s.execute(select(MessageRecord).where(MessageRecord.event_id == e.id))).scalar_one()
    assert (row.role, row.content, row.token_usage) == ("user", "耳机想退款", None)
    assert row.session_id == "p-1"


async def test_assistant_message_carries_token_usage(db_session_factory) -> None:
    w = await _writer(db_session_factory, "p-2")
    e = await w.append(EventType.ASSISTANT_MESSAGE, {"content": "好的", "token_usage": 42})
    async with db_session_factory() as s:
        row = (await s.execute(select(MessageRecord).where(MessageRecord.event_id == e.id))).scalar_one()
    assert (row.role, row.token_usage) == ("assistant", 42)


async def test_tool_call_opens_invocation(db_session_factory) -> None:
    w = await _writer(db_session_factory, "p-3")
    e = await w.append(EventType.TOOL_CALL, {"tool_name": "refund_apply", "args": {"order_id": "1024"}})
    async with db_session_factory() as s:
        row = (await s.execute(select(ToolInvocationRecord).where(ToolInvocationRecord.event_id == e.id))).scalar_one()
    assert row.status == InvocationStatus.RUNNING
    assert row.args == {"order_id": "1024"} and row.finished_at is None


async def test_tool_result_closes_invocation(db_session_factory) -> None:
    w = await _writer(db_session_factory, "p-4")
    call = await w.append(EventType.TOOL_CALL, {"tool_name": "order_query", "args": {}})
    await w.append(
        EventType.TOOL_RESULT,
        {"tool_call_id": call.id, "result": {"status": "已发货"}, "digest": "已发货", "latency_ms": 88},
    )
    async with db_session_factory() as s:
        row = (
            await s.execute(select(ToolInvocationRecord).where(ToolInvocationRecord.event_id == call.id))
        ).scalar_one()
    assert row.status == InvocationStatus.SUCCEEDED
    assert (row.result_digest, row.latency_ms) == ("已发货", 88)
    assert row.finished_at is not None


async def test_tool_error_marks_failed(db_session_factory) -> None:
    w = await _writer(db_session_factory, "p-5")
    call = await w.append(EventType.TOOL_CALL, {"tool_name": "order_query", "args": {}})
    await w.append(EventType.TOOL_ERROR, {"tool_call_id": call.id, "error": "下游超时", "retry_count": 2})
    async with db_session_factory() as s:
        row = (
            await s.execute(select(ToolInvocationRecord).where(ToolInvocationRecord.event_id == call.id))
        ).scalar_one()
    assert row.status == InvocationStatus.FAILED
    assert (row.error, row.retry_count) == ("下游超时", 2)


async def test_tool_result_without_call_is_projection_error(db_session_factory) -> None:
    """write-ahead 顺序被破坏的响亮失败——绝不静默造一行。"""
    w = await _writer(db_session_factory, "p-6")
    with pytest.raises(ProjectionError, match="write-ahead"):
        await w.append(EventType.TOOL_RESULT, {"tool_call_id": "不存在", "digest": "x"})


async def test_summary_updated_writes_session_projection(db_session_factory) -> None:
    async with db_session_factory() as s:
        async with s.begin():
            s.add(SessionRecord(id="p-7", tenant_id="t-a", user_id="u-1"))
    w = await _writer(db_session_factory, "p-7")
    await w.append(EventType.SUMMARY_UPDATED, {"summary": "用户想退耳机", "covers_through_seq": 6})
    async with db_session_factory() as s:
        row = (await s.execute(select(SessionRecord).where(SessionRecord.id == "p-7"))).scalar_one()
    assert row.summary == "用户想退耳机"


async def test_summary_without_session_row_is_projection_error(db_session_factory) -> None:
    w = await _writer(db_session_factory, "p-8")
    with pytest.raises(ProjectionError, match="p-8"):
        await w.append(EventType.SUMMARY_UPDATED, {"summary": "x"})


async def test_missing_required_payload_field_is_loud(db_session_factory) -> None:
    """payload 契约被机器强制：缺字段是 bug 信号，报错必须点名字段。"""
    w = await _writer(db_session_factory, "p-9")
    with pytest.raises(ProjectionError, match="content"):
        await w.append(EventType.USER_MESSAGE, {})


async def test_events_without_projection_are_noop(db_session_factory) -> None:
    w = await _writer(db_session_factory, "p-10")
    await w.append(EventType.LLM_CALL, {"tier": "standard"})
    await w.append(EventType.LOOP_TERMINATED, {"reason": "completed"})
    async with db_session_factory() as s:
        n_msg = (
            await s.execute(select(func.count()).select_from(MessageRecord).where(MessageRecord.session_id == "p-10"))
        ).scalar_one()
        n_inv = (
            await s.execute(
                select(func.count()).select_from(ToolInvocationRecord).where(ToolInvocationRecord.session_id == "p-10")
            )
        ).scalar_one()
    assert (n_msg, n_inv) == (0, 0)


async def test_projection_failure_rolls_back_event_too(db_session_factory) -> None:
    """本交付的灵魂断言：事实与投影同生共死——投影失败，事件也不许留下。"""
    w = await _writer(db_session_factory, "p-11")
    with pytest.raises(ProjectionError):
        await w.append(EventType.SUMMARY_UPDATED, {"summary": "x"})  # 无会话行
    async with db_session_factory() as s:
        n = (
            await s.execute(select(func.count()).select_from(EventRecord).where(EventRecord.session_id == "p-11"))
        ).scalar_one()
    assert n == 0

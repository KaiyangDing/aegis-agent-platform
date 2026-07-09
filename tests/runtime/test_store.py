"""M2.2 交付①：五表模型的结构与约束测试（跑在真实 PG 上，夹具外层事务整体回滚）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from aegis.runtime.store import (
    ApprovalRecord,
    ApprovalStatus,
    EventRecord,
    InvocationStatus,
    MessageRecord,
    RunState,
    SessionRecord,
    ToolInvocationRecord,
)


def _session(sid: str = "s-1") -> SessionRecord:
    return SessionRecord(id=sid, tenant_id="t-a", user_id="u-1")


def _event(sid: str = "s-1", seq: int = 1, eid: str | None = None) -> EventRecord:
    return EventRecord(
        id=eid or f"evt-{sid}-{seq}",
        session_id=sid,
        run_id="r-1",
        seq=seq,
        type="user_message",
        schema_version=1,
        payload={"content": "你好"},
    )


def test_run_state_values_are_stable() -> None:
    assert {s.value for s in RunState} == {"idle", "running", "awaiting_approval", "failed"}


def test_invocation_status_values_are_stable() -> None:
    assert {s.value for s in InvocationStatus} == {"running", "succeeded", "failed"}


def test_approval_status_values_are_stable() -> None:
    """五态（02 §3）：超时与撤回是一等状态，不是 rejected 的变体。"""
    assert {s.value for s in ApprovalStatus} == {"pending", "approved", "rejected", "cancelled", "expired"}


async def test_session_defaults(db_session) -> None:
    s = _session()
    db_session.add(s)
    await db_session.flush()
    await db_session.refresh(s)
    assert s.run_state == RunState.IDLE
    assert s.lease_generation == 0 and s.recovery_count == 0
    assert s.lease_owner is None and s.lease_expires_at is None and s.summary is None
    assert s.created_at is not None and s.updated_at is not None


async def test_event_payload_jsonb_roundtrip(db_session) -> None:
    """payload 存原文的物理基础：JSONB 中文/嵌套结构无损往返。"""
    db_session.add(_event(eid="evt-json"))
    await db_session.flush()
    got = (await db_session.execute(select(EventRecord).where(EventRecord.id == "evt-json"))).scalar_one()
    assert got.payload == {"content": "你好"}
    assert got.schema_version == 1


async def test_event_seq_unique_within_session(db_session) -> None:
    """第二道防线：会话锁失效时，并发双写必有一边吃 IntegrityError，绝无静默交错。"""
    db_session.add(_event(seq=7, eid="evt-a"))
    await db_session.flush()
    db_session.add(_event(seq=7, eid="evt-b"))
    with pytest.raises(IntegrityError, match="uq_events_session_seq"):
        await db_session.flush()


async def test_event_seq_repeats_across_sessions(db_session) -> None:
    """约束的作用域必须是"会话内"——跨会话同 seq 是常态，不许误伤。"""
    db_session.add(_event("s-1", seq=1, eid="evt-s1"))
    db_session.add(_event("s-2", seq=1, eid="evt-s2"))
    await db_session.flush()


async def test_message_event_id_unique(db_session) -> None:
    """投影防重：同一源事件绝不派生两行消息。"""
    db_session.add(MessageRecord(session_id="s-1", event_id="evt-m", role="user", content="hi"))
    await db_session.flush()
    db_session.add(MessageRecord(session_id="s-1", event_id="evt-m", role="user", content="hi again"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_tool_invocation_defaults(db_session) -> None:
    inv = ToolInvocationRecord(session_id="s-1", event_id="evt-t1", tool_name="order_query", args={"order_id": "1024"})
    db_session.add(inv)
    await db_session.flush()
    await db_session.refresh(inv)
    assert inv.status == InvocationStatus.RUNNING
    assert inv.retry_count == 0 and inv.finished_at is None and inv.result_digest is None


async def test_approval_defaults(db_session) -> None:
    ap = ApprovalRecord(
        id="ap-1",
        session_id="s-1",
        tenant_id="t-a",
        tool_name="refund_apply",
        args={"order_id": "1024", "amount": 350},
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(ap)
    await db_session.flush()
    await db_session.refresh(ap)
    assert ap.status == ApprovalStatus.PENDING
    assert ap.operator_id is None and ap.decided_at is None and ap.event_id is None

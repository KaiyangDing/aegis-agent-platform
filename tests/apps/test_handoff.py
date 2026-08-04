"""M3.8 交付②：转人工——工单创建/摘要优先级（sessions.summary → 末三条 messages → 空话术）。"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from aegis.apps.support.handoff import create_handoff
from aegis.apps.support.mock_backend import client as client_mod
from aegis.apps.support.mock_backend.app import create_mock_api
from aegis.core.config import Settings
from aegis.runtime.store import MessageRecord, SessionRecord


@pytest.fixture
async def wired_mock(db_session_factory, monkeypatch):
    """mock 子应用建在测试工厂上，工具/handoff 的进程内通路重定向过去（自动还原）。"""
    app = create_mock_api(settings=Settings(), session_factory=db_session_factory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock") as c:
        monkeypatch.setattr(client_mod, "_client", c)
        yield c


async def _seed_session(factory, sid: str, *, summary: str | None = None) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=sid, tenant_id="t-svc", user_id="u-svc", summary=summary))


async def _seed_message(factory, sid: str, role: str, content: str) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(MessageRecord(session_id=sid, event_id=uuid4().hex, role=role, content=content))


async def test_create_handoff_prefers_session_summary(wired_mock, db_session_factory) -> None:
    """摘要优先级第一档：sessions.summary（M2.5 滚动摘要投影）非空则直接用。"""
    await _seed_session(db_session_factory, "s-ho-1", summary="用户咨询订单 A123 退款进度，已确认可退。")
    out = await create_handoff(
        factory=db_session_factory,
        session_id="s-ho-1",
        tenant_id="t-svc",
        user_id="u-svc",
        reason="user_requested",
        idempotency_key=uuid4().hex,
    )
    assert out["ticket_id"]
    assert out["reason"] == "user_requested"
    assert out["summary"] == "用户咨询订单 A123 退款进度，已确认可退。"


async def test_create_handoff_falls_back_to_last_three_messages(wired_mock, db_session_factory) -> None:
    """第二档：summary 空 → 拼最近 3 条 messages（保时序、带角色前缀）。"""
    await _seed_session(db_session_factory, "s-ho-2")
    for i in range(4):
        await _seed_message(db_session_factory, "s-ho-2", "user" if i % 2 == 0 else "assistant", f"消息{i}")
    out = await create_handoff(
        factory=db_session_factory,
        session_id="s-ho-2",
        tenant_id="t-svc",
        user_id="u-svc",
        reason="loop_limit",
        idempotency_key=uuid4().hex,
    )
    assert out["summary"] == "assistant: 消息1\nuser: 消息2\nassistant: 消息3"  # 最近 3 条、时序正向


async def test_create_handoff_empty_history_placeholder(wired_mock, db_session_factory) -> None:
    """第三档：全空 → 固定占位话术（工单不许空 detail 地开出去）。"""
    await _seed_session(db_session_factory, "s-ho-3")
    out = await create_handoff(
        factory=db_session_factory,
        session_id="s-ho-3",
        tenant_id="t-svc",
        user_id="u-svc",
        reason="user_requested",
        idempotency_key=uuid4().hex,
    )
    assert out["summary"] == "（无历史消息）"

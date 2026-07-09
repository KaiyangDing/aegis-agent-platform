"""M2.1 交付③：事件类型与 AgentEvent 的口径测试。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from aegis.runtime.events import SCHEMA_VERSION, AgentEvent, EventType


def test_event_type_values_are_stable() -> None:
    """13 类值快照（03 §5 表）。M2.2 若按 C8 增 summary_updated，先让这里红、过口径再改。"""
    assert {e.value for e in EventType} == {
        "user_message",
        "assistant_message",
        "llm_call",
        "llm_result",
        "tool_call",
        "tool_result",
        "tool_error",
        "approval_requested",
        "approval_decided",
        "approval_cancelled",
        "approval_expired",
        "loop_terminated",
        "handoff",
    }


def test_schema_version_is_one() -> None:
    """payload 契约当前版本。升版意味着新增解析器而不是改旧事件（03 §5）。"""
    assert SCHEMA_VERSION == 1


def test_agent_event_fields_and_frozen() -> None:
    e = AgentEvent(
        session_id="s-1",
        run_id="r-1",
        seq=1,
        type=EventType.USER_MESSAGE,
        payload={"content": "你好"},
    )
    assert e.schema_version == SCHEMA_VERSION
    assert e.type is EventType.USER_MESSAGE
    with pytest.raises(FrozenInstanceError):
        e.seq = 2  # type: ignore[misc]


@pytest.mark.parametrize("blank", ["session_id", "run_id"])
def test_agent_event_rejects_blank_ids(blank: str) -> None:
    kwargs: dict[str, Any] = dict(session_id="s", run_id="r", seq=1, type=EventType.HANDOFF, payload={})
    kwargs[blank] = ""
    with pytest.raises(ValueError, match=blank):
        AgentEvent(**kwargs)


@pytest.mark.parametrize("bad_seq", [0, -1])
def test_agent_event_rejects_bad_seq(bad_seq: int) -> None:
    with pytest.raises(ValueError, match="seq"):
        AgentEvent(
            session_id="s",
            run_id="r",
            seq=bad_seq,
            type=EventType.HANDOFF,
            payload={},
        )


def test_agent_event_rejects_bad_schema_version() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        AgentEvent(
            session_id="s",
            run_id="r",
            seq=1,
            type=EventType.HANDOFF,
            payload={},
            schema_version=0,
        )

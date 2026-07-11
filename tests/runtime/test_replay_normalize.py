"""M2.6 交付③：C31 事件等价归一化（plans/m2.6 §3.3 字段表逐行钉死）。

`normalize_events(A) == normalize_events(B)` 即行为轨迹等价——M2.12"中断-恢复
逐事件一致"与 M4.3 CI 的断言本体。豁免要滴得掉、业务差异要保得住，双向都测。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.replay import normalize_events


def _event(
    seq: int,
    type_: EventType,
    payload: dict[str, Any],
    *,
    id_: str | None = None,
    sid: str = "s-1",
    run: str = "r-1",
) -> AgentEvent:
    return AgentEvent(id=id_ or uuid4().hex, session_id=sid, run_id=run, seq=seq, type=type_, payload=payload)


def _tool_stream(prefix: str, *, seq0: int, run: str, latency: int) -> list[AgentEvent]:
    """一次工具调用的两事件流：uuid/会话/run/seq/latency 全部因流而异，业务内容相同。"""
    call_id = f"{prefix}-call-{uuid4().hex}"
    call = _event(
        seq0,
        EventType.TOOL_CALL,
        {"tool_name": "demo_refund", "args": {"order_id": "A-1"}},
        id_=call_id,
        sid=f"{prefix}-s",
        run=run,
    )
    result = _event(
        seq0 + 1,
        EventType.TOOL_RESULT,
        {"tool_call_id": call_id, "result": "ok", "latency_ms": latency},
        sid=f"{prefix}-s",
        run=run,
    )
    return [call, result]


def test_strips_exempt_top_level_keys() -> None:
    """豁免键只滴 payload 顶层（D12）：result 内层同名业务字段不受牵连。"""
    e = _event(
        1,
        EventType.TOOL_RESULT,
        {
            "tool_call_id": "tc-x",
            "result": {"usage": "内层同名不滴", "金额": 30},
            "digest": "d",
            "latency_ms": 12,
            "duration_ms": 3,
            "usage": {"prompt_tokens": 1},
            "prompt_tokens": 5,
            "completion_tokens": 6,
            "expires_at": "2026-07-11T00:00:00Z",
        },
    )
    p = normalize_events([e])[0]["payload"]
    assert set(p) == {"tool_call_id", "result", "digest"}
    assert p["result"] == {"usage": "内层同名不滴", "金额": 30}


def test_two_streams_differ_only_in_ids_and_latency_are_equal() -> None:
    """C31 灵魂断言：只有 id/会话/run/seq/latency 不同的两条流，归一化后逐事件相等。"""
    a = _tool_stream("a", seq0=1, run="r-a", latency=5)
    b = _tool_stream("b", seq0=7, run="r-b", latency=999)
    assert normalize_events(a) == normalize_events(b)


def test_tool_call_id_aliased_consistently() -> None:
    """幂等链保真：tool_result.payload.tool_call_id 与 tool_call 事件同指别名 e1。"""
    n = normalize_events(_tool_stream("a", seq0=1, run="r-a", latency=5))
    assert n[1]["payload"]["tool_call_id"] == "e1"


def test_approval_id_aliased_by_first_appearance() -> None:
    """审批单 uuid 每次不同、链路结构必须相同：两流均归一为 a1。"""

    def stream(av: str) -> list[AgentEvent]:
        return [
            _event(1, EventType.APPROVAL_REQUESTED, {"approval_id": av, "tool_name": "refund_apply"}),
            _event(2, EventType.APPROVAL_DECIDED, {"approval_id": av, "approved": True}),
        ]

    na = normalize_events(stream(f"ap-{uuid4().hex}"))
    nb = normalize_events(stream(f"ap-{uuid4().hex}"))
    assert na == nb
    assert na[0]["payload"]["approval_id"] == "a1"
    assert na[1]["payload"]["approval_id"] == "a1"


def test_content_difference_breaks_equality() -> None:
    """归一化没把断言归没：业务字段差一个字就不相等。"""
    a = [_event(1, EventType.ASSISTANT_MESSAGE, {"content": "您的订单已发货"})]
    b = [_event(1, EventType.ASSISTANT_MESSAGE, {"content": "您的订单已退款"})]
    assert normalize_events(a) != normalize_events(b)


def test_unknown_reference_kept_verbatim() -> None:
    """引用流外事件 id ⇒ 保留原值——两流该值不同则不相等（bug 要响亮暴露，不许被别名洗白）。"""
    a = [_event(1, EventType.TOOL_RESULT, {"tool_call_id": "流外-a", "result": "ok"})]
    b = [_event(1, EventType.TOOL_RESULT, {"tool_call_id": "流外-b", "result": "ok"})]
    assert normalize_events(a) != normalize_events(b)
    assert normalize_events(a)[0]["payload"]["tool_call_id"] == "流外-a"


def test_normalize_handles_decimal_via_json_roundtrip() -> None:
    """canonical JSON 往返：刚 yield 的事件（含 Decimal）与 DB 读回形态（已 JSON 化）可比。"""
    fresh = [_event(1, EventType.TOOL_CALL, {"tool_name": "refund", "args": {"amount": Decimal("30.50")}})]
    from_db = [_event(1, EventType.TOOL_CALL, {"tool_name": "refund", "args": {"amount": "30.50"}})]
    assert normalize_events(fresh) == normalize_events(from_db)

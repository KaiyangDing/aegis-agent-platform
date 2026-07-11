"""M2.7 交付①：循环骨架 + 文本直答链 + AgentRuntime 接线（plans/m2.7 §5.1 主干）。

回放驱动：FakeGateway 喂内存 cassette（M2.6 基建首次被总装消费），零真实调用（00 §6.0）。
本文件先钉 I4/I5/I7 三条不变量与 P2 无行防线；工具链与 I3 接线用例随交付②，
闸门与异常矩阵用例随交付③④（plans/m2.7 §8 切分）。
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from aegis.gateway.schema import StopChunk, TextDelta, UsageChunk
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.replay import Cassette, CassetteEntry, FakeGateway
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec
from aegis.runtime.store import EventRecord, MessageRecord

_SPEC = AgentSpec(system_prompt="你是演示客服，请简洁回答。")


def _text_cassette(session_id: str, *texts: str) -> Cassette:
    """每段文本一条 main 道条目：TextDelta → Usage → Stop(end_turn)——顺序不变量同真网关。"""
    entries = tuple(
        CassetteEntry(
            chunks=(
                TextDelta(text=text),
                UsageChunk(model="qwen-plus", prompt_tokens=20, completion_tokens=7),
                StopChunk(reason="end_turn"),
            )
        )
        for text in texts
    )
    return Cassette(session_id=session_id, scopes={"main": entries})


async def _run_collect(
    factory,
    session_id: str,
    *texts: str,
    user_input: str = "请问我的订单何时送达？",
) -> list[AgentEvent]:
    """组装 AgentRuntime 收集一次 run 的全部产出事件；顺手断言 cassette 放完（无多余调用）。"""
    gateway = FakeGateway(_text_cassette(session_id, *texts))
    runtime = AgentRuntime(gateway, factory)
    events = [event async for event in runtime.run(_SPEC, session_id, user_input)]
    gateway.assert_exhausted()
    return events


async def test_text_reply_completes_with_assistant_message(db_session_factory, make_session) -> None:
    """闸门 0 全链：user→llm_call→llm_result(ok)→assistant_message→loop_terminated(completed)。"""
    await make_session("lf-1")
    events = await _run_collect(db_session_factory, "lf-1", "已在派送中，预计明天送达。")
    assert [e.type for e in events] == [
        EventType.USER_MESSAGE,
        EventType.LLM_CALL,
        EventType.LLM_RESULT,
        EventType.ASSISTANT_MESSAGE,
        EventType.LOOP_TERMINATED,
    ]
    call = events[1].payload
    assert call["iteration"] == 1
    assert call["tier"] == "standard"
    assert call["input_tokens_est"] > 0
    result = events[2].payload
    assert result["status"] == "ok"
    assert result["text"] == "已在派送中，预计明天送达。"
    assert result["stop_reason"] == "end_turn"
    assert result["usage"] == {"prompt_tokens": 20, "completion_tokens": 7}
    assert result["tool_calls"] == []
    reply = events[3].payload
    assert reply["content"] == "已在派送中，预计明天送达。"
    assert reply["token_usage"] == 7  # =usage.completion_tokens（plans/m2.7 §4.6）
    done = events[4].payload
    assert done["reason"] == "completed"
    assert done["iteration"] == 1


async def test_run_yields_full_event_stream_in_seq_order(db_session_factory, make_session) -> None:
    """I4：yield 序 ≡ seq 序且从 1 连续；产出集合与落盘集合逐条相等（_Tap 不漏）。"""
    await make_session("lf-2")
    events = await _run_collect(db_session_factory, "lf-2", "好的。")
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    async with db_session_factory() as s:
        rows = (
            await s.execute(
                select(EventRecord.id, EventRecord.seq)
                .where(EventRecord.session_id == "lf-2")
                .order_by(EventRecord.seq)
            )
        ).all()
    assert [(e.id, e.seq) for e in events] == [(r.id, r.seq) for r in rows]


async def test_user_message_is_first_event_and_projected(db_session_factory, make_session) -> None:
    """I5 + D19：user_message 恒为首事件（loop 写入，API 层不旁路），并投影 messages 行。"""
    await make_session("lf-3")
    events = await _run_collect(db_session_factory, "lf-3", "好的。", user_input="帮我查订单 A-42")
    first = events[0]
    assert first.type is EventType.USER_MESSAGE
    assert first.seq == 1
    assert first.payload == {"content": "帮我查订单 A-42"}
    async with db_session_factory() as s:
        rows = (
            await s.execute(select(MessageRecord.role, MessageRecord.content).where(MessageRecord.session_id == "lf-3"))
        ).all()
    assert ("user", "帮我查订单 A-42") in {(r.role, r.content) for r in rows}


async def test_loop_terminated_is_always_last_and_unique(db_session_factory, make_session) -> None:
    """I7：每 run 恰一条 loop_terminated 且为末事件。"""
    await make_session("lf-4")
    events = await _run_collect(db_session_factory, "lf-4", "好的。")
    terminated = [e for e in events if e.type is EventType.LOOP_TERMINATED]
    assert len(terminated) == 1
    assert events[-1] is terminated[0]


async def test_missing_session_row_raises(db_session_factory) -> None:
    """P2 防线：无 sessions 行 → ValueError 报会话号，且零事件落盘（拒绝无身份起跑）。"""
    gateway = FakeGateway(_text_cassette("lf-none"))
    runtime = AgentRuntime(gateway, db_session_factory)
    with pytest.raises(ValueError, match="lf-none"):
        async for _ in runtime.run(_SPEC, "lf-none", "你好"):
            pass
    async with db_session_factory() as s:
        count = (
            await s.execute(select(func.count()).select_from(EventRecord).where(EventRecord.session_id == "lf-none"))
        ).scalar_one()
    assert count == 0

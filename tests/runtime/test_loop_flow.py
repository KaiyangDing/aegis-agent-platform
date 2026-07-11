"""M2.7 交付①②：循环骨架 + 文本直答链 + 工具分支与 I3 接线（plans/m2.7 §5.1）。

回放驱动：FakeGateway 喂内存 cassette（M2.6 基建首次被总装消费），零真实调用（00 §6.0）。
交付①钉 I4/I5/I7 三条不变量与 P2 无行防线；交付②补工具两轮链、回填协议（§7 坑 6）
与 I3 两条显式接线（timeout/budget——08 §8 #10）。闸门与异常矩阵用例在
test_loop_termination.py / test_loop_gateway_errors.py（交付②③④，plans/m2.7 §8 切分）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Sequence

import pytest
from sqlalchemy import func, select

from aegis.gateway.schema import (
    LLMChunk,
    LLMRequest,
    StopChunk,
    TextDelta,
    ToolCall,
    ToolCallChunk,
    UsageChunk,
)
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.replay import Cassette, CassetteEntry, FakeGateway
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec, ContextConfig, LoopPolicy
from aegis.runtime.store import EventRecord, MessageRecord
from aegis.runtime.tools import SideEffect, ToolContext, tool

_SPEC = AgentSpec(system_prompt="你是演示客服，请简洁回答。")


def _call(cid: str, name: str, args: str) -> ToolCall:
    return ToolCall(id=cid, name=name, arguments_json=args)


def _text_turn(text: str) -> list[LLMChunk]:
    """一轮纯文本输出：TextDelta → Usage → Stop(end_turn)——顺序不变量同真网关。"""
    return [
        TextDelta(text=text),
        UsageChunk(model="qwen-plus", prompt_tokens=20, completion_tokens=7),
        StopChunk(reason="end_turn"),
    ]


def _tool_turn(*calls: ToolCall) -> list[LLMChunk]:
    """一轮工具调用输出：ToolCallChunk* → Usage → Stop(tool_calls)。"""
    chunks: list[LLMChunk] = [ToolCallChunk(tool_call=c) for c in calls]
    chunks.append(UsageChunk(model="qwen-plus", prompt_tokens=30, completion_tokens=12))
    chunks.append(StopChunk(reason="tool_calls"))
    return chunks


def _cassette(session_id: str, *turns: list[LLMChunk], digest: list[LLMChunk] | None = None) -> Cassette:
    """按 main 道逐轮组带；digest 非 None 时另铺一条 tool_digest 道（C10 四道独立计数）。"""
    scopes: dict[str, tuple[CassetteEntry, ...]] = {"main": tuple(CassetteEntry(chunks=tuple(t)) for t in turns)}
    if digest is not None:
        scopes["tool_digest"] = (CassetteEntry(chunks=tuple(digest)),)
    return Cassette(session_id=session_id, scopes=scopes)


def _text_cassette(session_id: str, *texts: str) -> Cassette:
    """每段文本一条 main 道条目（交付①便捷形态）。"""
    return _cassette(session_id, *(_text_turn(t) for t in texts))


class _CaptureGateway:
    """记录每个 LLMRequest 并按脚本回放的替身（async def + yield：结构等价，§7 坑 1）。"""

    def __init__(self, scripts: Sequence[Sequence[LLMChunk]]) -> None:
        self.requests: list[LLMRequest] = []
        self._scripts = scripts

    async def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        self.requests.append(req)
        for chunk in self._scripts[len(self.requests) - 1]:
            yield chunk


@tool(side_effect=SideEffect.READ)
async def slow_lookup(ctx: ToolContext, key: str) -> dict:
    """慢查询（I3 超时接线测试专用）。"""
    await asyncio.sleep(0.3)
    return {"key": key}


@tool(side_effect=SideEffect.READ)
async def bulk_export(ctx: ToolContext, topic: str) -> dict:
    """导出大体积演示数据（I3 预算接线测试专用）。"""
    return {"topic": topic, "blob": "长" * 1_000}


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


async def test_tool_round_then_completion_event_chain(db_session_factory, make_session, demo_registry) -> None:
    """交付②·两轮链：tool_call/tool_result（executor 发射，经 _Tap 外流）夹在两次 LLM 步之间。"""
    await make_session("lf-6")
    spec = AgentSpec(system_prompt="你是演示客服。", tools=demo_registry.specs())
    gateway = FakeGateway(
        _cassette(
            "lf-6",
            _tool_turn(_call("call-1", "demo_order_query", '{"order_id": "A-1"}')),
            _text_turn("订单已发货。"),
        )
    )
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "lf-6", "帮我查订单 A-1")]
    gateway.assert_exhausted()
    assert [e.type for e in events] == [
        EventType.USER_MESSAGE,
        EventType.LLM_CALL,
        EventType.LLM_RESULT,
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
        EventType.LLM_CALL,
        EventType.LLM_RESULT,
        EventType.ASSISTANT_MESSAGE,
        EventType.LOOP_TERMINATED,
    ]
    assert events[1].payload["iteration"] == 1
    assert events[5].payload["iteration"] == 2
    assert events[2].payload["tool_calls"] == [
        {"id": "call-1", "name": "demo_order_query", "arguments_json": '{"order_id": "A-1"}'}
    ]
    assert events[3].payload == {"tool_name": "demo_order_query", "args": {"order_id": "A-1"}}
    assert events[4].payload["result"] == {"order_id": "A-1", "status": "已发货", "paid": 350}
    assert events[8].payload["reason"] == "completed"


async def test_tool_message_feeds_next_round_request(db_session_factory, make_session, demo_registry) -> None:
    """交付②·回填协议：结果用模型侧 ToolCall.id 配对（§7 坑 6），先 assistant(tool_calls) 后 tool；
    顺手钉请求接线：session_id 必带、deadline_s=I2、max_tokens=D3。"""
    await make_session("lf-7")
    spec = AgentSpec(system_prompt="你是演示客服。", tools=demo_registry.specs())
    gateway = _CaptureGateway(
        [
            _tool_turn(_call("call-9", "demo_order_query", '{"order_id": "A-2"}')),
            _text_turn("查到了。"),
        ]
    )
    runtime = AgentRuntime(gateway, db_session_factory)
    async for _ in runtime.run(spec, "lf-7", "查订单 A-2"):
        pass
    assert len(gateway.requests) == 2
    second = gateway.requests[1]
    assert second.session_id == "lf-7"
    assert second.deadline_s == spec.policy.llm_step_timeout_s  # I2：闸门 #2 即 deadline 传播
    assert second.max_tokens == spec.context_config.output_reserve  # D3：输出上限即余量层预算
    a_idx = next(i for i, m in enumerate(second.messages) if m.tool_calls)
    t_idx = next(i for i, m in enumerate(second.messages) if m.role == "tool")
    assert a_idx < t_idx  # 对话协议：先声明后回填
    tool_msg = second.messages[t_idx]
    assert tool_msg.tool_call_id == "call-9"  # 模型侧 id——幂等键（事件 id）严禁混入
    assert '"paid": 350' in tool_msg.content


async def test_policy_timeout_wired_into_executor(db_session_factory, make_session) -> None:
    """I3a：LoopPolicy.tool_step_timeout_s 显式传入 executor——0.05s 生效（默认 30 不再遮蔽），
    工具超时回填不终止（§4.7 闸门 #2 工具半边归 executor）。"""
    await make_session("lf-8")
    spec = AgentSpec(
        system_prompt="你是演示客服。",
        tools=(slow_lookup,),
        policy=LoopPolicy(tool_step_timeout_s=0.05),
    )
    gateway = FakeGateway(
        _cassette(
            "lf-8",
            _tool_turn(_call("call-s", "slow_lookup", '{"key": "k1"}')),
            _text_turn("查询超时了，请稍后再试。"),
        )
    )
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "lf-8", "查一下 k1")]
    gateway.assert_exhausted()
    errors = [e for e in events if e.type is EventType.TOOL_ERROR]
    assert len(errors) == 1
    assert "超时" in errors[0].payload["error"]
    assert events[-1].payload["reason"] == "completed"


async def test_context_budget_wired_into_executor(db_session_factory, make_session) -> None:
    """I3b：ContextConfig.tool_results_budget 显式传入 executor——200 生效触发收缩
    （默认 3000 收不到），且收缩摘要走 tool_digest 道（D15①/C10：不挤 main 计数）。"""
    await make_session("lf-9")
    spec = AgentSpec(
        system_prompt="你是演示客服。",
        tools=(bulk_export,),
        context_config=ContextConfig(tool_results_budget=200),
    )
    gateway = FakeGateway(
        _cassette(
            "lf-9",
            _tool_turn(_call("call-b", "bulk_export", '{"topic": "T"}')),
            _text_turn("已导出，内容较多先给你摘要。"),
            digest=_text_turn("要点：演示数据一批。"),
        )
    )
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "lf-9", "导出数据")]
    gateway.assert_exhausted()  # tool_digest 道恰被消费一次——摘要调用没挤进 main（§7 坑 14）
    result = next(e for e in events if e.type is EventType.TOOL_RESULT)
    assert result.payload["normalization"] == "summary"
    assert result.payload["injected"].startswith("（工具结果超预算，以下为摘要）")
    assert "要点：演示数据一批。" in result.payload["injected"]
    assert events[-1].payload["reason"] == "completed"


async def test_second_run_continues_seq_with_fresh_run_id(db_session_factory, make_session) -> None:
    """交付③·X5 + 单写者接续：同会话第二次 run——seq 接旧流尾递增（EventWriter.open 读流尾），
    run_id 每次启动新生成且 run 内一致。"""
    await make_session("lf-10")
    first = await _run_collect(db_session_factory, "lf-10", "第一轮回答。")
    second_gateway = FakeGateway(_text_cassette("lf-10", "第二轮回答。"))
    runtime = AgentRuntime(second_gateway, db_session_factory)
    second = [e async for e in runtime.run(_SPEC, "lf-10", "再问一句")]
    assert second[0].seq == first[-1].seq + 1
    assert len({e.run_id for e in first}) == 1
    assert len({e.run_id for e in second}) == 1
    assert first[0].run_id != second[0].run_id


async def test_multiple_tool_calls_one_turn_run_in_order(db_session_factory, make_session, demo_registry) -> None:
    """交付③·D20：一轮多工具调用顺序逐个执行（无并行）——事件次序与调用次序一致、配对各自闭合。"""
    await make_session("lf-11")
    spec = AgentSpec(system_prompt="你是演示客服。", tools=demo_registry.specs())
    gateway = FakeGateway(
        _cassette(
            "lf-11",
            _tool_turn(
                _call("c1", "demo_order_query", '{"order_id": "A-1"}'),
                _call("c2", "demo_ticket_create", '{"title": "催发货"}'),
            ),
            _text_turn("已查询订单并创建工单。"),
        )
    )
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "lf-11", "查订单并建工单")]
    gateway.assert_exhausted()
    tool_events = [e for e in events if e.type in (EventType.TOOL_CALL, EventType.TOOL_RESULT)]
    assert [e.type for e in tool_events] == [
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
    ]
    called = [e.payload["tool_name"] for e in tool_events if e.type is EventType.TOOL_CALL]
    assert called == ["demo_order_query", "demo_ticket_create"]
    assert events[-1].payload["reason"] == "completed"

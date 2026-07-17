"""M2.7 交付②③：终止闸门用例集（plans/m2.7 §5.2，§4.7 表逐行）。

交付②落闸门 #4（重复调用：D4 规范形 / D5 连续计数 / I8 打断不留事件）与 D6 幻觉记账；
交付③补齐闸门 #0(D18)/#1/#2 工具半边(X1)/#3(D8)/#5(D7)/#6(P1) 与 reason 值集契约。
（K3 占位测试已随 M2.9 挂起链路接管而移除——该行为由 test_suspend_resume.py 接续。）
零真实调用（00 §6.0）：FakeGateway 回放 + 本文件局部捕获替身。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Sequence
from typing import Literal

from aegis.gateway.schema import (
    LLMChunk,
    LLMRequest,
    StopChunk,
    TextDelta,
    ToolCall,
    ToolCallChunk,
    UsageChunk,
)
from aegis.runtime.events import EventType
from aegis.runtime.replay import Cassette, CassetteEntry, FakeGateway
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec, LoopPolicy, TerminationReason
from aegis.runtime.tools import SideEffect, ToolContext, tool


def _call(cid: str, name: str, args: str) -> ToolCall:
    return ToolCall(id=cid, name=name, arguments_json=args)


def _text_turn(text: str) -> list[LLMChunk]:
    return [
        TextDelta(text=text),
        UsageChunk(model="qwen-plus", prompt_tokens=20, completion_tokens=7),
        StopChunk(reason="end_turn"),
    ]


def _tool_turn(*calls: ToolCall) -> list[LLMChunk]:
    chunks: list[LLMChunk] = [ToolCallChunk(tool_call=c) for c in calls]
    chunks.append(UsageChunk(model="qwen-plus", prompt_tokens=30, completion_tokens=12))
    chunks.append(StopChunk(reason="tool_calls"))
    return chunks


def _empty_turn(stop: Literal["end_turn", "tool_calls", "max_tokens"] = "end_turn") -> list[LLMChunk]:
    """空输出轮：无文本无工具直接收尾——D7① 违规形态；stop="tool_calls" 时即 D7② 形态。"""
    return [UsageChunk(model="qwen-plus", prompt_tokens=15, completion_tokens=0), StopChunk(reason=stop)]


@tool(side_effect=SideEffect.WRITE, risk_exempt=True)
async def slow_ship(ctx: ToolContext, order_id: str) -> dict:
    """慢速发货指令（写工具超时 → RESULT_UNKNOWN 测试专用；低危写显式豁免审批）。"""
    await asyncio.sleep(0.3)
    return {"shipped": order_id}


def _cassette(session_id: str, *turns: list[LLMChunk]) -> Cassette:
    return Cassette(session_id=session_id, scopes={"main": tuple(CassetteEntry(chunks=tuple(t)) for t in turns)})


class _CaptureGateway:
    """记录每个 LLMRequest 并按脚本回放（打断话术只进下一轮请求，不进事件——须捕获请求断言）。"""

    def __init__(self, scripts: Sequence[Sequence[LLMChunk]]) -> None:
        self.requests: list[LLMRequest] = []
        self._scripts = scripts

    async def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        self.requests.append(req)
        for chunk in self._scripts[len(self.requests) - 1]:
            yield chunk


async def test_repeat_calls_break_prompt_injected(db_session_factory, make_session, demo_registry) -> None:
    """闸门 #4 打断（D5）：streak 达 3 该次不执行（I8：无 write-ahead 即无 tool_call 事件），
    打断话术以 role=tool 配对回填（§7 坑 8）；第二次调用故意做键序/空白抖动——D4 规范形不重置计数。"""
    await make_session("lt-1")
    spec = AgentSpec(system_prompt="你是演示客服。", tools=demo_registry.specs())
    gateway = _CaptureGateway(
        [
            _tool_turn(_call("c1", "demo_order_query", '{"order_id": "A-7"}')),
            _tool_turn(_call("c2", "demo_order_query", '{ "order_id" : "A-7" }')),  # 同义抖动
            _tool_turn(_call("c3", "demo_order_query", '{"order_id": "A-7"}')),
            _text_turn("我们换个方式核实这笔订单。"),
        ]
    )
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "lt-1", "查订单 A-7")]
    assert len([e for e in events if e.type is EventType.TOOL_CALL]) == 2  # 第 3 次被打断未执行（I8）
    fourth = gateway.requests[3]
    break_msg = next(m for m in fourth.messages if m.role == "tool" and m.tool_call_id == "c3")
    assert "未被执行" in break_msg.content
    assert "连续 3 次" in break_msg.content  # PROMPT_REPEAT_BREAK 以 policy 阈值格式化（I1）
    assert events[-1].payload["reason"] == "completed"


async def test_repeat_after_break_terminates(db_session_factory, make_session, demo_registry) -> None:
    """闸门 #4 终止（D5）：打断不清零，原样再犯 → repeated_calls；恰 limit+1=4 次 LLM 调用。"""
    await make_session("lt-2")
    spec = AgentSpec(system_prompt="你是演示客服。", tools=demo_registry.specs())
    same = '{"order_id": "A-8"}'
    gateway = _CaptureGateway(
        [
            _tool_turn(_call("c1", "demo_order_query", same)),
            _tool_turn(_call("c2", "demo_order_query", same)),
            _tool_turn(_call("c3", "demo_order_query", same)),
            _tool_turn(_call("c4", "demo_order_query", same)),
        ]
    )
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "lt-2", "查订单 A-8")]
    done = events[-1]
    assert done.payload["reason"] == "repeated_calls"
    assert len([e for e in events if e.type is EventType.LLM_CALL]) == 4  # repeat_call_limit + 1
    assert len([e for e in events if e.type is EventType.TOOL_CALL]) == 2  # 第 3 次打断、第 4 次触杀均未执行
    fallbacks = [e for e in events if e.type is EventType.ASSISTANT_MESSAGE]
    assert len(fallbacks) == 1
    assert "重复" in fallbacks[0].payload["content"]


async def test_varied_args_reset_repeat_streak(db_session_factory, make_session, demo_registry) -> None:
    """D5 重置：换了参数（规范形不同）即重置 streak——三次调用全部执行、无打断、正常完成。"""
    await make_session("lt-3")
    spec = AgentSpec(system_prompt="你是演示客服。", tools=demo_registry.specs())
    gateway = _CaptureGateway(
        [
            _tool_turn(_call("c1", "demo_order_query", '{"order_id": "A-9"}')),
            _tool_turn(_call("c2", "demo_order_query", '{"order_id": "A-9"}')),
            _tool_turn(_call("c3", "demo_order_query", '{"order_id": "B-1"}')),
            _text_turn("三笔都查到了。"),
        ]
    )
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "lt-3", "帮我查几笔订单")]
    assert len([e for e in events if e.type is EventType.TOOL_CALL]) == 3
    fed = [m for req in gateway.requests for m in req.messages if m.role == "tool"]
    assert all("未被执行" not in m.content for m in fed)
    assert events[-1].payload["reason"] == "completed"


async def test_hallucinated_tool_counts_as_violation(db_session_factory, make_session, demo_registry) -> None:
    """D6：幻觉工具名计入闸门 #5——一轮内三个不同幻觉名 → 连续违规 3 > 2，终止 protocol_violation。

    刻意用三个不同名字：同名同参会先被闸门 #4 打断（D5 次序在前），测不到违规记账；
    幻觉名在 executor 里也不 write-ahead——全程零 tool_call 事件。"""
    await make_session("lt-5")
    spec = AgentSpec(system_prompt="你是演示客服。", tools=demo_registry.specs())
    gateway = FakeGateway(
        _cassette(
            "lt-5",
            _tool_turn(
                _call("g1", "ghost_a", "{}"),
                _call("g2", "ghost_b", "{}"),
                _call("g3", "ghost_c", "{}"),
            ),
        )
    )
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "lt-5", "随便查查")]
    gateway.assert_exhausted()
    done = events[-1]
    assert done.payload["reason"] == "protocol_violation"
    assert "ghost_c" in done.payload["detail"]
    assert [e for e in events if e.type is EventType.TOOL_CALL] == []
    fallbacks = [e for e in events if e.type is EventType.ASSISTANT_MESSAGE]
    assert len(fallbacks) == 1
    assert "协议" in fallbacks[0].payload["content"]


async def test_max_tokens_truncated_text_completes(db_session_factory, make_session) -> None:
    """交付③·D18：max_tokens 截断但文本非空 → 按正常完成（截断是预算现实不是协议错误），
    stop_reason 随 llm_result 留痕。"""
    await make_session("lt-14")
    gateway = FakeGateway(
        _cassette(
            "lt-14",
            [
                TextDelta(text="回答到一半被截"),
                UsageChunk(model="qwen-plus", prompt_tokens=20, completion_tokens=7),
                StopChunk(reason="max_tokens"),
            ],
        )
    )
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(AgentSpec(system_prompt="你是演示客服。"), "lt-14", "讲讲政策")]
    result = next(e for e in events if e.type is EventType.LLM_RESULT)
    assert result.payload["stop_reason"] == "max_tokens"
    assert events[-1].payload["reason"] == "completed"


async def test_max_iterations_stops_with_handoff_suggestion(db_session_factory, make_session, demo_registry) -> None:
    """交付③·闸门 #1（D17）：完成 max_iterations 次调用后再欲发起即终止；话术含"转人工"；
    参数逐轮不同——刻意绕开闸门 #4，让 #1 独立触发（I1：阈值来自 policy 注入）。"""
    await make_session("lt-7")
    spec = AgentSpec(
        system_prompt="你是演示客服。",
        tools=demo_registry.specs(),
        policy=LoopPolicy(max_iterations=3),
    )
    gateway = _CaptureGateway(
        [
            _tool_turn(_call("c1", "demo_order_query", '{"order_id": "A-1"}')),
            _tool_turn(_call("c2", "demo_order_query", '{"order_id": "A-2"}')),
            _tool_turn(_call("c3", "demo_order_query", '{"order_id": "A-3"}')),
        ]
    )
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "lt-7", "把这几笔都查一遍")]
    done = events[-1]
    assert done.payload["reason"] == "max_iterations"
    assert done.payload["iteration"] == 3
    assert len([e for e in events if e.type is EventType.LLM_CALL]) == 3  # 第 4 次未发起
    fallbacks = [e for e in events if e.type is EventType.ASSISTANT_MESSAGE]
    assert len(fallbacks) == 1
    assert "转人工" in fallbacks[0].payload["content"]


async def test_write_tool_timeout_result_unknown_feeds_back(db_session_factory, make_session) -> None:
    """交付③·闸门 #2 工具半边 + X1：写工具超时 = 结果不明——回填"禁止重试"话术、循环不终止。

    executor 承担超时与话术（M2.4），loop 只透传观察结果；模型下一轮据此向用户说明。"""
    await make_session("lt-6")
    spec = AgentSpec(
        system_prompt="你是演示客服。",
        tools=(slow_ship,),
        policy=LoopPolicy(tool_step_timeout_s=0.05),
    )
    gateway = _CaptureGateway(
        [
            _tool_turn(_call("c1", "slow_ship", '{"order_id": "A-1"}')),
            _text_turn("发货指令结果不明，我先帮你查询确认。"),
        ]
    )
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "lt-6", "帮我发货")]
    errors = [e for e in events if e.type is EventType.TOOL_ERROR]
    assert len(errors) == 1
    assert "结果不明" in errors[0].payload["error"]
    feed = next(m for m in gateway.requests[1].messages if m.role == "tool")
    assert "禁止重试" in feed.content
    assert events[-1].payload["reason"] == "completed"


async def test_session_token_budget_precheck_stops_loudly(db_session_factory, make_session) -> None:
    """交付③·闸门 #3（D8）：调用前预检——预算不够时一次 LLM 调用都不发（零 llm_call），
    明确告知不静默截断（03:50）。main 道零条目：真发起调用会 CassetteMismatch 响亮失配。"""
    await make_session("lt-8")
    spec = AgentSpec(
        system_prompt="你是演示客服。",
        policy=LoopPolicy(session_token_budget=5),
    )
    gateway = FakeGateway(_cassette("lt-8"))
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "lt-8", "请给我讲讲你们的退货政策")]
    done = events[-1]
    assert done.payload["reason"] == "token_budget_exceeded"
    assert [e for e in events if e.type is EventType.LLM_CALL] == []
    fallbacks = [e for e in events if e.type is EventType.ASSISTANT_MESSAGE]
    assert len(fallbacks) == 1
    assert "预算" in fallbacks[0].payload["content"]


async def test_budget_counter_seeds_from_history_events(db_session_factory, make_session) -> None:
    """交付③·闸门 #3 会话级语义（D8）：新 run 起点从事件流重建——detail 报出的累计值
    恰等于首 run 留下的估算和（事件即事实源，计数可重放重建，不加新列）。"""
    await make_session("lt-9")
    g1 = FakeGateway(_cassette("lt-9", _text_turn("这是第一轮的回答，占一些 token。")))
    events1 = [
        e
        async for e in AgentRuntime(g1, db_session_factory).run(
            AgentSpec(system_prompt="你是演示客服。"), "lt-9", "先问一个问题"
        )
    ]
    call1 = next(e for e in events1 if e.type is EventType.LLM_CALL)
    result1 = next(e for e in events1 if e.type is EventType.LLM_RESULT)
    seed = call1.payload["input_tokens_est"] + result1.payload["output_tokens_est"]
    spec2 = AgentSpec(system_prompt="你是演示客服。", policy=LoopPolicy(session_token_budget=seed + 1))
    g2 = FakeGateway(_cassette("lt-9"))
    events2 = [e async for e in AgentRuntime(g2, db_session_factory).run(spec2, "lt-9", "再问一个")]
    done = events2[-1]
    assert done.payload["reason"] == "token_budget_exceeded"
    assert [e for e in events2 if e.type is EventType.LLM_CALL] == []
    assert f"累计估算 {seed} " in done.payload["detail"]  # 种子被丢会写成"累计估算 0"


async def test_protocol_violation_retry_then_terminate(db_session_factory, make_session) -> None:
    """交付③·闸门 #5（D7）：空输出/宣告工具却没给（①②两形态）→ role=user 纠错重试；
    连续 3 次（> limit=2）→ 终止；恰 protocol_retry_limit+1 次 LLM 调用。"""
    await make_session("lt-10")
    gateway = _CaptureGateway([_empty_turn(), _empty_turn("tool_calls"), _empty_turn()])
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(AgentSpec(system_prompt="你是演示客服。"), "lt-10", "在吗")]
    done = events[-1]
    assert done.payload["reason"] == "protocol_violation"
    assert len([e for e in events if e.type is EventType.LLM_CALL]) == 3
    second = gateway.requests[1]
    retry_msgs = [m for m in second.messages if m.role == "user" and "重新输出" in m.content]
    assert len(retry_msgs) == 1  # 纠错以 user 消息注入，不动 system 层（03 §3）
    assert len([e for e in events if e.type is EventType.ASSISTANT_MESSAGE]) == 1  # 仅兜底一条


async def test_valid_reply_resets_violation_count(db_session_factory, make_session, demo_registry) -> None:
    """交付③·闸门 #5 连续语义：两次违规后一轮合法工具调用清零计数——其后再两次违规仍可纠错。

    若计数不清零，第 3 次违规（累计口径）就会触杀；本用例走到第 6 轮正常完成即证明清零。"""
    await make_session("lt-11")
    spec = AgentSpec(system_prompt="你是演示客服。", tools=demo_registry.specs())
    gateway = _CaptureGateway(
        [
            _empty_turn(),
            _empty_turn(),
            _tool_turn(_call("c1", "demo_order_query", '{"order_id": "A-1"}')),
            _empty_turn(),
            _empty_turn(),
            _text_turn("查到了，订单已发货。"),
        ]
    )
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "lt-11", "查订单")]
    assert events[-1].payload["reason"] == "completed"
    assert len([e for e in events if e.type is EventType.LLM_CALL]) == 6


async def test_cancel_event_terminates_gracefully(db_session_factory, make_session) -> None:
    """交付③·闸门 #6（P1 拍板）：取消信号在 LLM 调用前检查点生效——优雅终止：
    无兜底话术（用户主动走的）、零 LLM 调用，已落盘事件即持久化状态。"""
    await make_session("lt-12")
    cancel = asyncio.Event()
    cancel.set()
    gateway = FakeGateway(_cassette("lt-12"))
    runtime = AgentRuntime(gateway, db_session_factory, cancel_event=cancel)
    events = [e async for e in runtime.run(AgentSpec(system_prompt="你是演示客服。"), "lt-12", "你好")]
    assert [e.type for e in events] == [EventType.USER_MESSAGE, EventType.LOOP_TERMINATED]
    assert events[-1].payload["reason"] == "cancelled"


async def test_terminated_payload_reason_values(db_session_factory, make_session) -> None:
    """交付③·回放契约：loop_terminated.reason 是 TerminationReason 值集里的字符串字面量
    （payload 一律 .value——§7 坑 9，构造/断言两侧不混枚举成员）。"""
    await make_session("lt-13")
    g = FakeGateway(_cassette("lt-13", _text_turn("好的。")))
    events = [
        e
        async for e in AgentRuntime(g, db_session_factory).run(
            AgentSpec(system_prompt="你是演示客服。"), "lt-13", "在吗"
        )
    ]
    reason = events[-1].payload["reason"]
    assert isinstance(reason, str)
    assert reason in {r.value for r in TerminationReason}

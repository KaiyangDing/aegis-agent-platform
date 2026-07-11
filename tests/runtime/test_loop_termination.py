"""M2.7 交付②起：终止闸门用例集（plans/m2.7 §5.2）。

本份先落闸门 #4（重复调用：D4 规范形 / D5 连续计数 / I8 打断不留事件）、
K3 占位（NEEDS_APPROVAL 回填继续，不碰 approvals）与 D6 幻觉记账；
闸门 #1/#3/#5/#6 的其余用例随交付③（异常矩阵接电后）补齐——plans/m2.7 §8 切分。
零真实调用（00 §6.0）：FakeGateway 回放 + 本文件局部捕获替身。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence

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
from aegis.runtime.events import EventType
from aegis.runtime.replay import Cassette, CassetteEntry, FakeGateway
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec
from aegis.runtime.store import ApprovalRecord


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


async def test_needs_approval_placeholder_feeds_back(db_session_factory, make_session, demo_registry) -> None:
    """K3 占位：NEEDS_APPROVAL 当普通观察结果回填继续——不开审批单、不写工具事件、不置状态。

    风险闸门先于 write-ahead（03 §4 次序），所以连 tool_call 事件都没有；
    挂起链路（审批单 + awaiting_approval）是 M2.9 的领地，本步 approvals 表必须零行。"""
    await make_session("lt-4")
    spec = AgentSpec(
        system_prompt="你是演示客服。",
        tools=demo_registry.specs(),
        tenant_config={"approval_threshold": 200},
    )
    gateway = _CaptureGateway(
        [
            _tool_turn(_call("c1", "demo_refund_apply", '{"order_id": "A-1", "amount": 350}')),
            _text_turn("这笔退款超过阈值，需要人工审批后才能执行。"),
        ]
    )
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "lt-4", "退 350 元")]
    assert events[-1].payload["reason"] == "completed"
    assert [e for e in events if e.type is EventType.TOOL_CALL] == []
    feed = next(m for m in gateway.requests[1].messages if m.role == "tool")
    assert feed.tool_call_id == "c1"
    assert "审批" in feed.content
    async with db_session_factory() as s:
        count = (
            await s.execute(select(func.count()).select_from(ApprovalRecord).where(ApprovalRecord.session_id == "lt-4"))
        ).scalar_one()
    assert count == 0


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

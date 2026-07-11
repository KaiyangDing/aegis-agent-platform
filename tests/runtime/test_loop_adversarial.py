"""M2.7 交付④：诱导死循环对抗用例（00 §6.1/§6.2 明文要求；plans/m2.7 §5.4）。

cassette 走文件形态入库 tests/cassettes/（K5 现场裁决）——它们同时是 M4.3 CI 回放
回归的资产池（00 §8.1 M4.3 行：cassette 输入 = M2.6 手写用例 + …）。四个脚本分别
诱导：同参数死循环 / 永远空输出 / 换参续跑不休 / token 烧穿——断言循环在六道闸门
下**有界终止**，绝不跑飞。资产由 scripts 外一次性脚本经 Cassette.save 生成（格式
由 M2.6 代码本身保证），重录流程见 tests/cassettes/README.md。
"""

from __future__ import annotations

from pathlib import Path

from aegis.runtime.events import EventType
from aegis.runtime.replay import Cassette, FakeGateway
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec, LoopPolicy

_CASSETTES = Path(__file__).resolve().parent.parent / "cassettes"  # 锚定文件自身，不依赖 cwd


def _load(name: str) -> Cassette:
    return Cassette.load(_CASSETTES / name)


async def test_induced_tool_loop_cassette_terminates_bounded(db_session_factory, make_session, demo_registry) -> None:
    """对抗①：模型每轮原样重复同一 (tool, args)——打断→再犯→repeated_calls；
    调用数与事件总数全部有界（闸门 #4 是这条路的天花板）。"""
    await make_session("adv-tool-loop")
    spec = AgentSpec(system_prompt="你是演示客服。", tools=demo_registry.specs())
    gateway = FakeGateway(_load("adversarial_tool_loop.json"))
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "adv-tool-loop", "查订单 A-13")]
    gateway.assert_exhausted()
    assert events[-1].payload["reason"] == "repeated_calls"
    assert len([e for e in events if e.type is EventType.LLM_CALL]) == 4  # repeat_call_limit + 1
    assert len([e for e in events if e.type is EventType.TOOL_CALL]) == 2  # 第 3 次打断、第 4 次触杀均未执行
    assert len(events) == 15  # 1 user + 4×(llm_call+llm_result) + 2×(tool_call+tool_result) + 兜底 + 终止


async def test_forever_violation_cassette_terminates(db_session_factory, make_session) -> None:
    """对抗②：模型永远空输出——纠错 2 次仍违规 → protocol_violation；恰 limit+1=3 次调用。"""
    await make_session("adv-empty")
    gateway = FakeGateway(_load("adversarial_empty_replies.json"))
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(AgentSpec(system_prompt="你是演示客服。"), "adv-empty", "在吗")]
    gateway.assert_exhausted()
    assert events[-1].payload["reason"] == "protocol_violation"
    assert len([e for e in events if e.type is EventType.LLM_CALL]) == 3  # protocol_retry_limit + 1
    assert len(events) == 9  # 1 user + 3×(llm_call+llm_result) + 兜底 + 终止


async def test_runaway_iterations_capped(db_session_factory, make_session, demo_registry) -> None:
    """对抗③：模型永远"再查一次"（参数轮换绕开闸门 #4）——max_iterations 兜底，恰 10 次 llm_call。"""
    await make_session("adv-runaway")
    spec = AgentSpec(system_prompt="你是演示客服。", tools=demo_registry.specs())
    gateway = FakeGateway(_load("adversarial_runaway_iterations.json"))
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "adv-runaway", "把这些订单全部核对一遍")]
    gateway.assert_exhausted()
    done = events[-1]
    assert done.payload["reason"] == "max_iterations"
    assert len([e for e in events if e.type is EventType.LLM_CALL]) == 10  # 默认 max_iterations（D17）
    assert len([e for e in events if e.type is EventType.TOOL_CALL]) == 10  # 每轮参数不同，全部真执行
    fallback = next(e for e in events if e.type is EventType.ASSISTANT_MESSAGE)
    assert "转人工" in fallback.payload["content"]


async def test_token_burn_stopped_by_budget(db_session_factory, make_session, demo_registry) -> None:
    """对抗④：巨型参数反复调工具烧 token——会话预算闸门（D8 调用前预检）先于轮数拦停。

    cassette 铺了 10 轮"模型还想继续"，故意不 assert_exhausted：剩余条目就是被闸门
    拦下的意图本身。计数用估算尺（C25），cassette 里的 usage 数字不参与闸门。"""
    await make_session("adv-burn")
    spec = AgentSpec(
        system_prompt="你是演示客服。",
        tools=demo_registry.specs(),
        policy=LoopPolicy(session_token_budget=2_000),
    )
    gateway = FakeGateway(_load("adversarial_token_burn.json"))
    runtime = AgentRuntime(gateway, db_session_factory)
    events = [e async for e in runtime.run(spec, "adv-burn", "把这些都处理掉")]
    done = events[-1]
    assert done.payload["reason"] == "token_budget_exceeded"
    burns = len([e for e in events if e.type is EventType.LLM_CALL])
    assert 1 <= burns < spec.policy.max_iterations  # 预算先于轮数触发（00 §6.1 三级预算 L2 级）
    fallbacks = [e for e in events if e.type is EventType.ASSISTANT_MESSAGE]
    assert len(fallbacks) == 1
    assert "预算" in fallbacks[0].payload["content"]

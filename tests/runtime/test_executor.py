"""M2.4 交付①：执行器前厅——校验、风险闸门、连败禁用；write-ahead 之前的一切。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.executor import OutcomeKind, ToolExecutor
from aegis.runtime.tools import SideEffect, ToolContext, ToolRegistry, tool

TENANT_CFG = {"approval_threshold": 200}


class _NullSink:
    """前厅测试替身：顺便断言执行器在 write-ahead 之前绝不写事件。"""

    session_id = "s-front"
    run_id = "r-front"

    async def append(self, event_type: EventType, payload: Mapping[str, Any]) -> AgentEvent:
        raise AssertionError("前厅路径不该写事件")


def _executor(reg: ToolRegistry) -> ToolExecutor:
    return ToolExecutor(reg, _NullSink(), tenant_id="t-a", user_id="u-1", tenant_config=TENANT_CFG)


def test_outcome_kind_values_are_stable() -> None:
    """五种结局的值快照：它们会进事件 payload 与回放断言。"""
    assert {k.value for k in OutcomeKind} == {"ok", "error", "result_unknown", "needs_approval", "disabled"}


async def test_unknown_tool_is_error_without_streak(demo_registry: ToolRegistry) -> None:
    """幻觉工具名：回填点名可用工具；没有工具可禁用，不进连败账。"""
    ex = _executor(demo_registry)
    out = await ex.execute("hallucinated_tool", "{}")
    assert out.kind is OutcomeKind.ERROR
    assert "不存在" in out.content and "demo_order_query" in out.content


async def test_broken_json_fed_back(demo_registry: ToolRegistry) -> None:
    ex = _executor(demo_registry)
    out = await ex.execute("demo_order_query", "{broken")
    assert out.kind is OutcomeKind.ERROR and "JSON" in out.content


async def test_non_object_json_rejected(demo_registry: ToolRegistry) -> None:
    out = await _executor(demo_registry).execute("demo_order_query", "[1, 2]")
    assert out.kind is OutcomeKind.ERROR and "对象" in out.content


async def test_hallucinated_param_named_in_feedback(demo_registry: ToolRegistry) -> None:
    """extra=forbid 的报错必须点名多余字段——模型看到才能自我修正。"""
    ex = _executor(demo_registry)
    out = await ex.execute("demo_refund_apply", '{"order_id": "1024", "amount": 80, "coupon": "X"}')
    assert out.kind is OutcomeKind.ERROR and "coupon" in out.content


async def test_lax_numeric_string_then_gate_hits(demo_registry: ToolRegistry) -> None:
    """校验宽容度与导出 schema 一致（lax）：数字字符串放行；随后闸门按值命中审批。"""
    out = await _executor(demo_registry).execute("demo_refund_apply", '{"order_id": "1", "amount": "350"}')
    assert out.kind is OutcomeKind.NEEDS_APPROVAL


def _gate_boom(args, cfg) -> bool:
    raise RuntimeError("闸门自己炸了")


@tool(side_effect=SideEffect.WRITE, risk_policy=_gate_boom)
async def demo_gate_bug(ctx: ToolContext, amount: int) -> dict:
    """风险闸门会崩溃的演示工具。"""
    return {}


async def test_gate_crash_fails_closed() -> None:
    """安全闸门 fail-closed（§2.2）：风险评估自己炸了 → 操作不执行，绝不放行。"""
    ex = _executor(ToolRegistry([demo_gate_bug]))
    out = await ex.execute("demo_gate_bug", '{"amount": 1}')
    assert out.kind is OutcomeKind.ERROR
    assert "fail-closed" in out.content and "未执行" in out.content


async def test_two_failures_disable_tool_for_run(demo_registry: ToolRegistry) -> None:
    """同一工具连败 2 次本轮禁用（03 §4）：第 2 败即宣告，之后合法参数也不放行。"""
    ex = _executor(demo_registry)
    await ex.execute("demo_order_query", "{broken")
    second = await ex.execute("demo_order_query", "{broken")
    assert "本轮已禁用" in second.content
    third = await ex.execute("demo_order_query", '{"order_id": "1"}')
    assert third.kind is OutcomeKind.DISABLED


async def test_streak_is_per_tool_and_per_run(demo_registry: ToolRegistry) -> None:
    """连败账按工具分开记；执行器每 run 一个实例——禁用不跨 run。"""
    ex = _executor(demo_registry)
    await ex.execute("demo_order_query", "{broken")
    await ex.execute("demo_order_query", "{broken")
    out_b = await ex.execute("demo_ticket_create", '{"title": 1}')
    assert out_b.kind is OutcomeKind.ERROR  # B 工具首败：只是 ERROR，不受 A 连累
    fresh = _executor(demo_registry)
    out = await fresh.execute("demo_order_query", "{broken")  # 新 run：同名工具回到首败待遇
    assert out.kind is OutcomeKind.ERROR and "本轮已禁用" not in out.content

"""M2.4 交付②：执行核心——write-ahead、超时取更严、读重试写不重试、X1 结果不明。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest
from sqlalchemy import select

from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.executor import OutcomeKind, ToolExecutor
from aegis.runtime.store import (
    EventRecord,
    EventStoreUnavailable,
    EventWriter,
    InvocationStatus,
    ToolInvocationRecord,
)
from aegis.runtime.tools import SideEffect, ToolContext, ToolRegistry, tool

TENANT_CFG = {"approval_threshold": 200}


def _sleep_recorder(into: list[float]):
    async def _sleep(delay: float) -> None:
        into.append(delay)

    return _sleep


async def _make(
    factory, reg: ToolRegistry, sid: str, *, default_timeout_s: float = 5.0, slept: list[float] | None = None
) -> ToolExecutor:
    w = await EventWriter.open(factory, sid, "r-1")
    return ToolExecutor(
        reg,
        w,
        tenant_id="t-a",
        user_id="u-1",
        tenant_config=TENANT_CFG,
        default_timeout_s=default_timeout_s,
        sleep=_sleep_recorder(slept) if slept is not None else _sleep_recorder([]),
    )


@tool(side_effect=SideEffect.READ)
async def echo_ctx(ctx: ToolContext, ping: str) -> dict:
    """回显注入的身份与幂等键。"""
    return {"ping": ping, "tool_call_id": ctx.tool_call_id, "user": ctx.user_id}


async def test_write_ahead_key_reaches_handler(db_session_factory) -> None:
    """④ 的核心断言：handler 拿到的 ctx.tool_call_id 就是先落盘的 tool_call 事件 id。"""
    ex = await _make(db_session_factory, ToolRegistry([echo_ctx]), "ex-1")
    out = await ex.execute("echo_ctx", '{"ping": "pong"}')
    assert out.kind is OutcomeKind.OK and out.tool_call_id is not None
    async with db_session_factory() as s:
        call_row = (await s.execute(select(EventRecord).where(EventRecord.id == out.tool_call_id))).scalar_one()
    assert call_row.type == "tool_call" and call_row.payload["tool_name"] == "echo_ctx"
    assert f'"tool_call_id": "{out.tool_call_id}"' in out.content  # handler 真拿到了同一把钥匙


async def test_gate_passed_write_executes_and_closes_invocation(db_session_factory, demo_registry) -> None:
    """低于阈值的写：闸门放行 → write-ahead → 执行 → tool_result 事件闭合审计投影。"""
    ex = await _make(db_session_factory, demo_registry, "ex-2")
    out = await ex.execute("demo_refund_apply", '{"order_id": "1024", "amount": 80}')
    assert out.kind is OutcomeKind.OK and "refunded" in out.content
    async with db_session_factory() as s:
        inv = (
            await s.execute(select(ToolInvocationRecord).where(ToolInvocationRecord.event_id == out.tool_call_id))
        ).scalar_one()
    assert inv.status == InvocationStatus.SUCCEEDED and inv.finished_at is not None


async def test_success_resets_fail_streak(db_session_factory) -> None:
    """连败账是"连续"败：成功一次清零，之后单次失败不触发禁用。"""
    ex = await _make(db_session_factory, ToolRegistry([echo_ctx]), "ex-3")
    await ex.execute("echo_ctx", "{broken")
    assert (await ex.execute("echo_ctx", '{"ping": "x"}')).kind is OutcomeKind.OK
    again = await ex.execute("echo_ctx", "{broken")
    assert again.kind is OutcomeKind.ERROR and "本轮已禁用" not in again.content


async def test_read_timeout_final_error(db_session_factory) -> None:
    @tool(side_effect=SideEffect.READ, timeout_s=0.05)
    async def slow_read(ctx: ToolContext) -> dict:
        """睡不醒的读工具。"""
        await asyncio.sleep(5)
        return {}

    ex = await _make(db_session_factory, ToolRegistry([slow_read]), "ex-4")
    out = await ex.execute("slow_read", "{}")
    assert out.kind is OutcomeKind.ERROR and "超时" in out.content
    async with db_session_factory() as s:
        inv = (
            await s.execute(select(ToolInvocationRecord).where(ToolInvocationRecord.event_id == out.tool_call_id))
        ).scalar_one()
    assert inv.status == InvocationStatus.FAILED


async def test_read_retries_then_succeeds(db_session_factory) -> None:
    """读可退避重试：前两次抖、第三次成；事件里 retry_count 记账。"""
    calls = {"n": 0}

    @tool(side_effect=SideEffect.READ, retries=2)
    async def flaky_read(ctx: ToolContext) -> dict:
        """时好时坏的读工具。"""
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("抖一下")
        return {"ok": calls["n"]}

    slept: list[float] = []
    ex = await _make(db_session_factory, ToolRegistry([flaky_read]), "ex-5", slept=slept)
    out = await ex.execute("flaky_read", "{}")
    assert out.kind is OutcomeKind.OK and calls["n"] == 3
    assert slept == [pytest.approx(0.2), pytest.approx(0.4)]
    async with db_session_factory() as s:
        result_row = (
            await s.execute(
                select(EventRecord).where(EventRecord.session_id == "ex-5", EventRecord.type == "tool_result")
            )
        ).scalar_one()
    assert result_row.payload["retry_count"] == 2


async def test_write_timeout_result_unknown_x1(db_session_factory) -> None:
    """X1：写工具超时=结果不明——副作用可能已生效，回填禁止重试并引导查询确认。"""

    @tool(side_effect=SideEffect.WRITE, risk_exempt=True, timeout_s=0.05)
    async def slow_write(ctx: ToolContext) -> dict:
        """睡不醒的写工具。"""
        await asyncio.sleep(5)
        return {}

    ex = await _make(db_session_factory, ToolRegistry([slow_write]), "ex-6")
    out = await ex.execute("slow_write", "{}")
    assert out.kind is OutcomeKind.RESULT_UNKNOWN
    assert "禁止重试" in out.content and "查询" in out.content
    async with db_session_factory() as s:
        inv = (
            await s.execute(select(ToolInvocationRecord).where(ToolInvocationRecord.event_id == out.tool_call_id))
        ).scalar_one()
    assert inv.status == InvocationStatus.FAILED and "结果不明" in (inv.error or "")


async def test_write_exception_single_attempt_error(db_session_factory) -> None:
    """写工具明确失败：单次尝试（绝不自动重试）、ERROR 回填、tool_error 留痕。"""
    calls = {"n": 0}

    @tool(side_effect=SideEffect.WRITE, risk_exempt=True)
    async def boom_write(ctx: ToolContext) -> dict:
        """一碰就炸的写工具。"""
        calls["n"] += 1
        raise RuntimeError("下游拒绝")

    ex = await _make(db_session_factory, ToolRegistry([boom_write]), "ex-7")
    out = await ex.execute("boom_write", "{}")
    assert out.kind is OutcomeKind.ERROR and "下游拒绝" in out.content
    assert calls["n"] == 1


async def test_stricter_timeout_wins(db_session_factory) -> None:
    """超时取更严：工具自报 99s，循环级默认 0.05s——生效的是 0.05s。"""

    @tool(side_effect=SideEffect.READ, timeout_s=99.0)
    async def optimistic(ctx: ToolContext) -> dict:
        """自以为有 99 秒的工具。"""
        await asyncio.sleep(5)
        return {}

    ex = await _make(db_session_factory, ToolRegistry([optimistic]), "ex-8", default_timeout_s=0.05)
    out = await ex.execute("optimistic", "{}")
    assert out.kind is OutcomeKind.ERROR and "超时" in out.content


class _DeadSink:
    """基础设施故障替身：append 即炸。"""

    session_id = "s-dead"
    run_id = "r-dead"

    async def append(self, event_type: EventType, payload: Mapping[str, Any]) -> AgentEvent:
        raise EventStoreUnavailable("PG 挂了")


async def test_infra_failure_propagates() -> None:
    """世界分界：工具世界的结局进 outcome，基础设施故障裸传播给循环处置。"""
    ex = ToolExecutor(ToolRegistry([echo_ctx]), _DeadSink(), tenant_id="t", user_id="u", tenant_config=TENANT_CFG)
    with pytest.raises(EventStoreUnavailable):
        await ex.execute("echo_ctx", '{"ping": "x"}')

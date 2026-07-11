"""M2.7 交付③：六类网关异常 → 循环分支映射矩阵（plans/m2.7 §4.4，逐行一测）。

零真实调用（00 §6.0）：请求级异常用 complete 即抛的 _RaisingGateway；流级中断用
首轮半截的 _FlakyGateway；基础设施故障用"先健康后永久断连"的 _DyingFactory
（对齐 test_event_store._FlakyFactory 的构造口径与 test_executor_exec 的世界分界）。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from aegis.gateway.errors import (
    BudgetExceeded,
    GatewayError,
    GatewayExhausted,
    GatewayOverloadedError,
    GatewayRejected,
    GatewayStreamInterrupted,
    TenantQuotaExceeded,
)
from aegis.gateway.schema import LLMChunk, LLMRequest, StopChunk, TextDelta, UsageChunk
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec
from aegis.runtime.store import EventRecord, EventStoreUnavailable, SessionFactory

_SPEC = AgentSpec(system_prompt="你是演示客服。")


class _RaisingGateway:
    """complete 即抛（首块之前）——请求级异常矩阵用，无须 fixture 化（plans/m2.7 §5.0）。"""

    def __init__(self, exc: GatewayError) -> None:
        self._exc = exc

    async def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        raise self._exc
        yield  # 不可达；使本函数成为 async 生成器


class _FlakyGateway:
    """首轮吐半截文本后抛流级中断（死因挂 __cause__），次轮完整——D10 作废重发用。"""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        self.calls += 1
        if self.calls == 1:
            yield TextDelta(text="这半截话不应出现在最终回复里")
            raise GatewayStreamInterrupted("流在首块后中断") from ConnectionError("connection reset")
        yield TextDelta(text="重发后的完整回答。")
        yield UsageChunk(model="qwen-plus", prompt_tokens=20, completion_tokens=7)
        yield StopChunk(reason="end_turn")


class _DyingFactory:
    """前 healthy 次透传真工厂，之后永远抛连接级故障——身份读得到、事件写不进。"""

    def __init__(self, real: SessionFactory, healthy: int) -> None:
        self._real = real
        self._left = healthy

    def __call__(self) -> AsyncSession:
        if self._left > 0:
            self._left -= 1
            return self._real()
        raise OperationalError("boom", None, RuntimeError("connection refused"))


async def _run(factory, session_id: str, gateway) -> list[AgentEvent]:
    runtime = AgentRuntime(gateway, factory)
    return [e async for e in runtime.run(_SPEC, session_id, "帮我查一下")]


def _assert_failed_pair(events: list[AgentEvent], *, reason: str, cause: str, fallback_substr: str | None) -> None:
    """终止型矩阵行的公共形状：llm_result(failed,cause) 配对（I6）+ 终止原因/cause + 话术有无。"""
    result = next(e for e in events if e.type is EventType.LLM_RESULT)
    assert result.payload["status"] == "failed"
    assert result.payload["cause"] == cause
    done = events[-1]
    assert done.type is EventType.LOOP_TERMINATED
    assert done.payload["reason"] == reason
    assert done.payload["cause"] == cause
    calls = [e for e in events if e.type is EventType.LLM_CALL]
    results = [e for e in events if e.type is EventType.LLM_RESULT]
    assert len(calls) == len(results) == 1  # I6：failed 也配对，不留孤儿 llm_call
    fallbacks = [e for e in events if e.type is EventType.ASSISTANT_MESSAGE]
    if fallback_substr is None:
        assert fallbacks == []  # I9：C6 禁话术
    else:
        assert len(fallbacks) == 1
        assert fallback_substr in fallbacks[0].payload["content"]


async def test_gateway_exhausted_maps_to_step_timeout(db_session_factory, make_session) -> None:
    """§4.4 行 1：重试与 fallback 用尽（deadline 耗尽的浮出面）→ step_timeout + 兜底话术。"""
    await make_session("lg-1")
    events = await _run(db_session_factory, "lg-1", _RaisingGateway(GatewayExhausted("全部候选耗尽")))
    _assert_failed_pair(events, reason="step_timeout", cause="gateway_exhausted", fallback_substr="暂时不可用")


async def test_overloaded_maps_to_step_timeout(db_session_factory, make_session) -> None:
    """§4.4 行 2：本地连接池过载与上游耗尽同语义——步作废 + step_timeout。"""
    await make_session("lg-2")
    events = await _run(db_session_factory, "lg-2", _RaisingGateway(GatewayOverloadedError("连接池排队超时")))
    _assert_failed_pair(events, reason="step_timeout", cause="gateway_overloaded", fallback_substr="暂时不可用")


async def test_budget_exceeded_maps_to_token_budget(db_session_factory, make_session) -> None:
    """§4.4 行 3（D9）：L1 请求级预算 → token_budget_exceeded，cause 区分层级。"""
    await make_session("lg-3")
    events = await _run(db_session_factory, "lg-3", _RaisingGateway(BudgetExceeded("单请求预算超限")))
    _assert_failed_pair(events, reason="token_budget_exceeded", cause="l1_request_budget", fallback_substr="预算")


async def test_tenant_quota_maps_to_token_budget(db_session_factory, make_session) -> None:
    """§4.4 行 4（D9）：租户配额与预算同终止原因，cause=l1_tenant_quota。"""
    await make_session("lg-4")
    events = await _run(db_session_factory, "lg-4", _RaisingGateway(TenantQuotaExceeded("租户月度配额耗尽")))
    _assert_failed_pair(events, reason="token_budget_exceeded", cause="l1_tenant_quota", fallback_substr="预算")


async def test_gateway_rejected_terminates_without_fallback(db_session_factory, make_session) -> None:
    """§4.4 行 5（C6/I9）：确定性拒绝=bug 信号——零兜底话术，detail 带错误文本（L1 已消毒）。"""
    await make_session("lg-5")
    events = await _run(db_session_factory, "lg-5", _RaisingGateway(GatewayRejected("API key 无效")))
    _assert_failed_pair(events, reason="gateway_rejected", cause="gateway_rejected", fallback_substr=None)
    assert "API key 无效" in events[-1].payload["detail"]


async def test_stream_interrupted_voids_step_and_retries_next_iteration(db_session_factory, make_session) -> None:
    """§4.4 行 6（D10）：半截丢弃不入上下文、interrupted→ok 配对序列、重发消耗迭代数。"""
    await make_session("lg-6")
    events = await _run(db_session_factory, "lg-6", _FlakyGateway())
    statuses = [e.payload["status"] for e in events if e.type is EventType.LLM_RESULT]
    assert statuses == ["interrupted", "ok"]
    calls = [e for e in events if e.type is EventType.LLM_CALL]
    assert [c.payload["iteration"] for c in calls] == [1, 2]  # I6 全配对 + D17 重发计入迭代
    interrupted = next(e for e in events if e.type is EventType.LLM_RESULT)
    assert "connection reset" in interrupted.payload["detail"]  # 死因在 __cause__ 随 detail 留痕
    reply = next(e for e in events if e.type is EventType.ASSISTANT_MESSAGE)
    assert reply.payload["content"] == "重发后的完整回答。"
    assert "半截" not in reply.payload["content"]
    assert events[-1].payload["reason"] == "completed"


async def test_infra_error_propagates_out_of_run(db_session_factory, make_session) -> None:
    """§4.4 末行：基础设施故障不翻译不兜底——EventStoreUnavailable 裸穿出 run()。

    工厂前 2 次放行（身份读取、EventWriter.open 读流尾），写 user_message 起永久断连：
    短退避重试 3 次耗尽 → 原始异常出面；事件零落盘（半截不留）。
    """
    await make_session("lg-7")
    dying = _DyingFactory(db_session_factory, healthy=2)
    runtime = AgentRuntime(_RaisingGateway(GatewayExhausted("不该被调到")), dying)
    with pytest.raises(EventStoreUnavailable):
        async for _ in runtime.run(_SPEC, "lg-7", "你好"):
            pass
    async with db_session_factory() as s:
        count = (
            await s.execute(select(func.count()).select_from(EventRecord).where(EventRecord.session_id == "lg-7"))
        ).scalar_one()
    assert count == 0

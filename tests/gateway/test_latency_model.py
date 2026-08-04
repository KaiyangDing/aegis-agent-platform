"""M5.2 交付①：LatencyModelProvider 四测（时序不进 CI——sleep 走记录桩，00 §2.2）。"""

from __future__ import annotations

import pytest

from aegis.core.config import Settings
from aegis.gateway.providers.latency_model import LatencyModelProvider
from aegis.gateway.schema import LLMRequest, Message, StopChunk, TextDelta, UsageChunk


def _req() -> LLMRequest:
    return LLMRequest(tier="standard", messages=[Message(role="user", content="压测")], tenant_id="t-lt")


class _SleepRecorder:
    """记录桩：断言延迟计划而非真实耗时（test_executor_exec 先例）。"""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


async def test_chunk_sequence_shape() -> None:
    """完整流形状：N×TextDelta → UsageChunk → StopChunk（缓存完整性守卫兼容的收尾）。"""
    provider = LatencyModelProvider(response_tokens=5, sleep=_SleepRecorder())
    chunks = [c async for c in provider.complete(_req(), "qwen-plus")]
    assert [type(c) for c in chunks[:5]] == [TextDelta] * 5
    assert isinstance(chunks[5], UsageChunk) and isinstance(chunks[6], StopChunk)
    assert len(chunks) == 7


async def test_usage_reports_response_tokens() -> None:
    provider = LatencyModelProvider(response_tokens=8, sleep=_SleepRecorder())
    chunks = [c async for c in provider.complete(_req(), "qwen-turbo")]
    usage = chunks[-2]
    assert isinstance(usage, UsageChunk)
    assert usage.completion_tokens == 8
    assert usage.model == "qwen-turbo"  # model 回显入参（计量行按它计价）


def test_prod_forbids_loadtest_upstream() -> None:
    """替身是实验件：带上生产=全部真实流量打进假上游——配置错误启动时炸。"""
    with pytest.raises(ValueError):
        Settings(app_env="prod", loadtest_upstream=True)


async def test_timing_params_default_pinned() -> None:
    """口径参数钉死：首 token 0.8s + 20 tok/s（00 §9.1 写死；改参数=简历口径漂移）。
    断言的是**延迟计划**（sleep 调用序列）非真实耗时——时序不进 CI。"""
    recorder = _SleepRecorder()
    provider = LatencyModelProvider(response_tokens=3, sleep=recorder)
    async for _ in provider.complete(_req(), "qwen-plus"):
        pass
    assert recorder.calls[0] == pytest.approx(0.8)
    assert recorder.calls[1:] == [pytest.approx(1.0 / 20.0)] * 3

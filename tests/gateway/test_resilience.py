import pytest

from aegis.gateway import resilience
from aegis.gateway.errors import (
    AuthError,
    ProviderServerError,
    ProviderTimeoutError,
    RateLimitedError,
)
from aegis.gateway.resilience import RetryPolicy, complete_with_retry
from aegis.gateway.schema import LLMRequest, Message, StopChunk, TextDelta, UsageChunk

OK_CHUNKS = [
    TextDelta(text="好"),
    UsageChunk(model="m", prompt_tokens=1, completion_tokens=1),
    StopChunk(reason="end_turn"),
]


class ScriptedProvider:
    """按剧本演出的假供应商：先按序抛完 failures，然后正常产出 chunks。"""

    name = "scripted"

    def __init__(self, failures: list[Exception] | None = None):
        self.failures = list(failures or [])
        self.calls = 0

    async def complete(self, req, model):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        for c in OK_CHUNKS:
            yield c


class HalfwayExploder:
    """吐出首块后爆炸——用来验证'首块之后不重试'。"""

    name = "boom"

    def __init__(self):
        self.calls = 0

    async def complete(self, req, model):
        self.calls += 1
        yield TextDelta(text="half")
        raise ProviderServerError("boom", "mid-stream")


def make_req() -> LLMRequest:
    return LLMRequest(tier="fast", tenant_id="t1", messages=[Message(role="user", content="x")])


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    """替换测试接缝：记录每次退避时长，且不真的睡。"""
    recorded: list[float] = []

    async def fake_sleep(d: float) -> None:
        recorded.append(d)

    monkeypatch.setattr(resilience, "_sleep", fake_sleep)
    return recorded


@pytest.fixture
def no_jitter(monkeypatch) -> None:
    """满抖动取上界，让退避序列变得可断言。"""
    monkeypatch.setattr(resilience, "_uniform", lambda a, b: b)


async def collect(provider, policy=None) -> list:
    return [c async for c in complete_with_retry(provider, make_req(), "m", policy)]


async def test_no_failure_passthrough(sleeps):
    p = ScriptedProvider()
    assert await collect(p) == OK_CHUNKS
    assert p.calls == 1
    assert sleeps == []


async def test_retries_then_succeeds(sleeps, no_jitter):
    p = ScriptedProvider([ProviderTimeoutError("x", "t"), ProviderServerError("x", "5xx")])
    assert await collect(p) == OK_CHUNKS
    assert p.calls == 3  # 失败 2 次 + 成功 1 次
    assert len(sleeps) == 2


async def test_honors_retry_after(sleeps):
    p = ScriptedProvider([RateLimitedError("x", "busy", retry_after=3.0)])
    await collect(p)
    assert sleeps == [3.0]  # 服务端说等 3 秒，就等 3 秒，不套抖动


async def test_backoff_is_exponential_with_cap(sleeps, no_jitter):
    p = ScriptedProvider([ProviderServerError("x", "e")] * 3)
    policy = RetryPolicy(max_attempts=4, base_backoff=0.5, max_backoff=1.5)
    await collect(p, policy)
    assert sleeps == [0.5, 1.0, 1.5]  # 0.5 → 1.0 → (2.0 被削顶到) 1.5


async def test_non_retryable_fails_immediately(sleeps):
    p = ScriptedProvider([AuthError("x", "bad key")])
    with pytest.raises(AuthError):
        await collect(p)
    assert p.calls == 1
    assert sleeps == []


async def test_gives_up_after_max_attempts(sleeps, no_jitter):
    p = ScriptedProvider([ProviderTimeoutError("x", "t")] * 3)
    with pytest.raises(ProviderTimeoutError):
        await collect(p, RetryPolicy(max_attempts=3))
    assert p.calls == 3
    assert len(sleeps) == 2


async def test_no_retry_after_first_chunk(sleeps):
    p = HalfwayExploder()
    got = []
    with pytest.raises(ProviderServerError):
        async for c in complete_with_retry(p, make_req(), "m"):
            got.append(c)
    assert got == [TextDelta(text="half")]  # 半截已流出，绝不能重试造成重复输出
    assert p.calls == 1
    assert sleeps == []


async def test_total_timeout_budget_stops_retrying(sleeps):
    p = ScriptedProvider([ProviderTimeoutError("x", "t")])
    with pytest.raises(ProviderTimeoutError):
        await collect(p, RetryPolicy(total_timeout=0.0))  # 预算为零：一次都不许等
    assert p.calls == 1
    assert sleeps == []

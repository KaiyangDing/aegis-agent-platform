import pytest

from aegis.gateway import resilience
from aegis.gateway.errors import (
    GatewayExhausted,
    GatewayOverloadedError,
    GatewayStreamInterrupted,
    ProviderServerError,
    RateLimitedError,
    TenantQuotaExceeded,
)
from aegis.gateway.resilience import RetryPolicy
from aegis.gateway.router import Candidate, GatewayLimits, LLMGateway, parse_routes
from aegis.gateway.schema import LLMRequest, Message, StopChunk, TextDelta, UsageChunk

OK_CHUNKS = [
    TextDelta(text="ok"),
    UsageChunk(model="m", prompt_tokens=1, completion_tokens=1),
    StopChunk(reason="end_turn"),
]


class FakeProvider:
    """script 里每项对应一次调用：Exception=开局即炸；list=正常吐块。"""

    def __init__(self, name: str, script: list):
        self.name = name
        self.script = list(script)
        self.calls = 0
        self.models: list[str] = []  # 记录每次被要求跑的模型——锁死 cand.model 的传递

    async def complete(self, req, model):
        self.calls += 1
        self.models.append(model)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        for c in item:
            yield c


class HalfwayProvider:
    def __init__(self, name: str):
        self.name = name
        self.calls = 0

    async def complete(self, req, model):
        self.calls += 1
        yield TextDelta(text="half")
        raise ProviderServerError(self.name, "mid-stream")


class StubBreaker:
    def __init__(self, decisions: dict[str, str] | None = None):
        self.decisions = decisions or {}
        self.successes: list[str] = []
        self.failures: list[str] = []
        self.releases: list[str] = []

    async def allow(self, provider: str) -> str:
        return self.decisions.get(provider, "allow")

    async def on_success(self, provider: str) -> None:
        self.successes.append(provider)

    async def on_failure(self, provider: str) -> None:
        self.failures.append(provider)

    async def release_probe(self, provider: str) -> None:
        self.releases.append(provider)


class StubLimiter:
    def __init__(self, deny: set[str] | None = None):
        self.deny = deny or set()
        self.asked: list[str] = []

    async def wait_take(self, scope, rate, capacity, *, max_wait=10.0, cost=1.0) -> bool:
        self.asked.append(scope)
        return scope not in self.deny


@pytest.fixture(autouse=True)
def no_backoff_sleep(monkeypatch):
    async def nosleep(d: float) -> None: ...

    monkeypatch.setattr(resilience, "_sleep", nosleep)


def make_req(tier: str = "fast") -> LLMRequest:
    return LLMRequest(tier=tier, tenant_id="t1", messages=[Message(role="user", content="x")])


def make_gw(
    providers: list, breaker=None, limiter=None, **kw
) -> tuple[LLMGateway, StubBreaker, StubLimiter]:
    breaker = breaker or StubBreaker()
    limiter = limiter or StubLimiter()
    gw = LLMGateway(
        providers={p.name: p for p in providers},
        routes={"fast": [Candidate(p.name, f"model-{p.name}") for p in providers]},
        breaker=breaker,
        limiter=limiter,
        limits=GatewayLimits(max_wait=0.1),
        **kw,
    )
    return gw, breaker, limiter


async def collect(gw: LLMGateway) -> list:
    return [c async for c in gw.complete(make_req())]


async def test_first_candidate_success_short_circuits():
    p1, p2 = FakeProvider("p1", [OK_CHUNKS]), FakeProvider("p2", [OK_CHUNKS])
    gw, breaker, _ = make_gw([p1, p2])
    assert await collect(gw) == OK_CHUNKS
    assert (p1.calls, p2.calls) == (1, 0)
    assert breaker.successes == ["p1"]


async def test_breaker_deny_skips_provider_without_calling_it():
    p1, p2 = FakeProvider("p1", [OK_CHUNKS]), FakeProvider("p2", [OK_CHUNKS])
    gw, _, limiter = make_gw([p1, p2], breaker=StubBreaker({"p1": "deny"}))
    assert await collect(gw) == OK_CHUNKS
    assert (p1.calls, p2.calls) == (0, 1)  # p1 一次都没被打扰——秒拒的意义
    # 断言强度（加固 C）：deny 的供应商连限流队都不该排——若限流被挪到熔断前，这里变红
    assert "provider:p1" not in limiter.asked


async def test_server_error_counts_to_breaker_then_falls_back():
    p1 = FakeProvider("p1", [ProviderServerError("p1", "boom")])
    p2 = FakeProvider("p2", [OK_CHUNKS])
    gw, breaker, _ = make_gw([p1, p2], retry_policy=RetryPolicy(max_attempts=1))
    assert await collect(gw) == OK_CHUNKS
    assert breaker.failures == ["p1"]
    assert breaker.successes == ["p2"]
    # 断言强度（加固 C）：fallback 站必须用自己的 model——若误绑链首 model，这里变红
    assert p2.models == ["model-p2"]


async def test_retry_happens_inside_candidate_before_fallback():
    # p1 第一次失败、第二次成功：重试在站内消化，p2 根本不用出场
    p1 = FakeProvider("p1", [ProviderServerError("p1", "blip"), OK_CHUNKS])
    p2 = FakeProvider("p2", [OK_CHUNKS])
    gw, breaker, _ = make_gw([p1, p2])  # 默认策略 max_attempts=3
    assert await collect(gw) == OK_CHUNKS
    assert (p1.calls, p2.calls) == (2, 0)
    assert breaker.failures == []  # 站内自愈，不记熔断账


async def test_midstream_failure_never_falls_back():
    p1, p2 = HalfwayProvider("p1"), FakeProvider("p2", [OK_CHUNKS])
    gw, breaker, _ = make_gw([p1, p2])
    got = []
    # 加固 B 契约：流中断以 GatewayStreamInterrupted 出面，原始死因在 __cause__
    with pytest.raises(GatewayStreamInterrupted) as ei:
        async for c in gw.complete(make_req()):
            got.append(c)
    assert isinstance(ei.value.__cause__, ProviderServerError)
    assert got == [TextDelta(text="half")]  # 半截已流出
    assert p2.calls == 0  # 红线一：绝不换路重放
    assert breaker.failures == ["p1"]  # 但账照记


async def test_all_candidates_fail_raises_exhausted_with_cause():
    p1 = FakeProvider("p1", [ProviderServerError("p1", "a")])
    p2 = FakeProvider("p2", [ProviderServerError("p2", "b")])
    gw, breaker, _ = make_gw([p1, p2], retry_policy=RetryPolicy(max_attempts=1))
    with pytest.raises(GatewayExhausted) as ei:
        await collect(gw)
    assert isinstance(ei.value.__cause__, ProviderServerError)  # 异常链保留最后死因
    assert breaker.failures == ["p1", "p2"]


async def test_rate_limited_falls_back_without_breaker_count():
    p1 = FakeProvider("p1", [RateLimitedError("p1", "busy")])
    p2 = FakeProvider("p2", [OK_CHUNKS])
    gw, breaker, _ = make_gw([p1, p2], retry_policy=RetryPolicy(max_attempts=1))
    assert await collect(gw) == OK_CHUNKS
    assert breaker.failures == []  # 429 不是"上游死了"，不进熔断账本


async def test_tenant_quota_exhausted_fails_before_any_provider():
    p1 = FakeProvider("p1", [OK_CHUNKS])
    gw, _, _ = make_gw([p1], limiter=StubLimiter(deny={"tenant:t1"}))
    # 加固 B 契约：租户配额是契约内类型，不再冒充某个供应商的 429
    with pytest.raises(TenantQuotaExceeded):
        await collect(gw)
    assert p1.calls == 0  # 红线二：租户配额环外把关


async def test_provider_scope_limit_skips_to_next():
    p1, p2 = FakeProvider("p1", [OK_CHUNKS]), FakeProvider("p2", [OK_CHUNKS])
    gw, _, limiter = make_gw([p1, p2], limiter=StubLimiter(deny={"provider:p1"}))
    assert await collect(gw) == OK_CHUNKS
    assert (p1.calls, p2.calls) == (0, 1)


async def test_probe_decision_gets_single_attempt():
    # p1 半开探测：首次失败后不重试（探针一次定胜负），直接记账换路
    p1 = FakeProvider("p1", [ProviderServerError("p1", "still down"), OK_CHUNKS])
    p2 = FakeProvider("p2", [OK_CHUNKS])
    gw, breaker, _ = make_gw([p1, p2], breaker=StubBreaker({"p1": "probe"}))
    assert await collect(gw) == OK_CHUNKS
    assert p1.calls == 1  # 若走了默认策略会是 2（重试后成功）
    assert breaker.failures == ["p1"]


async def test_fault_injection_hits_only_target():
    p1, p2 = FakeProvider("p1", [OK_CHUNKS]), FakeProvider("p2", [OK_CHUNKS])
    gw, breaker, _ = make_gw(
        [p1, p2],
        retry_policy=RetryPolicy(max_attempts=1),
        fault_rate=1.0,
        fault_targets=frozenset({"p1:model-p1"}),
    )
    assert await collect(gw) == OK_CHUNKS
    assert (p1.calls, p2.calls) == (0, 1)  # p1 被注入器拦在门外，p2 不受影响
    assert breaker.failures == ["p1"]  # 注入的故障走完整的真实路径


def test_parse_routes_rejects_bad_entries():
    with pytest.raises(ValueError):
        parse_routes({"fast": ["no-colon-here"]}, {"bailian"})
    with pytest.raises(ValueError):
        parse_routes({"fast": ["ghost:qwen-flash"]}, {"bailian"})


class StubCache:
    def __init__(self, hit: list | None = None):
        self.hit = hit
        self.puts: list[list] = []

    async def get(self, req):
        return self.hit

    async def put(self, req, chunks):
        self.puts.append(list(chunks))


async def test_cache_hit_short_circuits_everything():
    p1 = FakeProvider("p1", [OK_CHUNKS])
    gw, breaker, limiter = make_gw([p1], cache=StubCache(hit=OK_CHUNKS))
    got = await collect(gw)
    assert p1.calls == 0
    assert limiter.asked == []  # 连租户配额都没问——最外圈短路
    usage = [c for c in got if isinstance(c, UsageChunk)][0]
    assert usage.cached is True  # 回放的账单盖了缓存章


async def test_cache_miss_stores_full_stream():
    p1 = FakeProvider("p1", [OK_CHUNKS])
    cache = StubCache(hit=None)
    gw, _, _ = make_gw([p1], cache=cache)
    await collect(gw)
    assert cache.puts == [OK_CHUNKS]  # 完整流入库


async def test_midstream_failure_is_never_cached():
    p1 = HalfwayProvider("p1")
    cache = StubCache(hit=None)
    gw, _, _ = make_gw([p1], cache=cache)
    with pytest.raises(GatewayStreamInterrupted):
        async for _ in gw.complete(make_req()):
            pass
    assert cache.puts == []  # 事故绝不能变成可重放的事故


# ---------- 审计加固 A ----------


class ExplodingCache:
    """在指定操作上抛连接错误——模拟 Redis 抖动时缓存必须退化而非拖死主链路。"""

    def __init__(self, explode_on: str):
        self.explode_on = explode_on
        self.puts: list[list] = []

    async def get(self, req):
        if self.explode_on == "get":
            raise ConnectionError("redis down")
        return None

    async def put(self, req, chunks):
        if self.explode_on == "put":
            raise ConnectionError("redis down")
        self.puts.append(list(chunks))


async def test_cache_get_failure_degrades_to_miss():
    p1 = FakeProvider("p1", [OK_CHUNKS])
    gw, _, _ = make_gw([p1], cache=ExplodingCache("get"))
    assert await collect(gw) == OK_CHUNKS  # 请求毫发无损，只是没省到钱
    assert p1.calls == 1


async def test_cache_put_failure_does_not_fail_completed_request():
    p1 = FakeProvider("p1", [OK_CHUNKS])
    gw, _, _ = make_gw([p1], cache=ExplodingCache("put"))
    # 已经成功的请求绝不能因为"写缓存失败"以异常收尾
    assert await collect(gw) == OK_CHUNKS


async def test_local_overload_neither_counted_nor_rerouted():
    p1 = FakeProvider("p1", [GatewayOverloadedError("本地连接池排队超时")])
    p2 = FakeProvider("p2", [OK_CHUNKS])
    gw, breaker, _ = make_gw([p1, p2])
    with pytest.raises(GatewayOverloadedError):
        await collect(gw)
    assert breaker.failures == []  # 本地过载不给供应商记熔断账
    assert p2.calls == 0  # 也不换路——所有候选共用同一个连接池


async def test_unrouted_tier_fails_cleanly_without_consuming_quota():
    p1 = FakeProvider("p1", [OK_CHUNKS])
    gw, _, limiter = make_gw([p1])  # 路由表里只有 fast
    with pytest.raises(GatewayExhausted):
        async for _ in gw.complete(make_req(tier="strong")):
            pass
    assert limiter.asked == []  # 配置问题在消耗任何配额之前干净失败


def test_parse_routes_requires_all_three_tiers():
    with pytest.raises(ValueError, match="缺少档位"):
        parse_routes({"fast": ["bailian:qwen-flash"]}, {"bailian"})


def test_parse_routes_rejects_empty_chain():
    full = {
        "fast": ["bailian:a"],
        "standard": [],
        "strong": ["bailian:b"],
    }
    with pytest.raises(ValueError, match="候选链为空"):
        parse_routes(full, {"bailian"})


async def test_probe_token_released_when_result_is_no_verdict():
    # 探针半路吃了 429：不构成熔断裁决，令牌必须归还（否则半开期空转 probe_ttl 秒）
    p1 = FakeProvider("p1", [RateLimitedError("p1", "busy")])
    p2 = FakeProvider("p2", [OK_CHUNKS])
    gw, breaker, _ = make_gw(
        [p1, p2],
        breaker=StubBreaker({"p1": "probe"}),
        retry_policy=RetryPolicy(max_attempts=1),
    )
    assert await collect(gw) == OK_CHUNKS
    assert breaker.releases == ["p1"]
    assert breaker.failures == []


async def test_probe_token_released_when_limiter_blocks_the_probe():
    p1, p2 = FakeProvider("p1", [OK_CHUNKS]), FakeProvider("p2", [OK_CHUNKS])
    gw, breaker, _ = make_gw(
        [p1, p2],
        breaker=StubBreaker({"p1": "probe"}),
        limiter=StubLimiter(deny={"provider:p1"}),
    )
    assert await collect(gw) == OK_CHUNKS
    assert p1.calls == 0
    assert breaker.releases == ["p1"]  # 领了令牌没打出去 → 还回去


class ClosingTrackedProvider:
    """finally 记录关闭——验证消费者挂断时 GeneratorExit 同步穿透到最内层。"""

    def __init__(self, name: str):
        self.name = name
        self.closed = False

    async def complete(self, req, model):
        try:
            yield TextDelta(text="a")
            yield TextDelta(text="b")
        finally:
            self.closed = True


async def test_consumer_close_propagates_to_provider_synchronously():
    p = ClosingTrackedProvider("p1")
    gw, _, _ = make_gw([p])
    agen = gw.complete(make_req())
    assert isinstance(await anext(agen), TextDelta)
    await agen.aclose()  # 消费者提前挂断（SSE 客户端关页面的最小复现）
    # 没有 aclosing 链时，内层生成器要等 GC 终结器异步收尸——此断言会红
    assert p.closed

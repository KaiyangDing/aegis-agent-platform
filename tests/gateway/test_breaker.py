import asyncio
import uuid

import redis.asyncio as aioredis

from aegis.gateway.breaker import CircuitBreaker


def name() -> str:
    return f"prov-{uuid.uuid4().hex[:8]}"  # 每个测试独立命名空间，互不污染


def make_breaker(r: aioredis.Redis) -> CircuitBreaker:
    return CircuitBreaker(r, failure_threshold=3, open_seconds=1, probe_ttl=5)


async def test_closed_allows_by_default(r):
    b, p = make_breaker(r), name()
    assert await b.allow(p) == "allow"


async def test_failures_below_threshold_keep_allowing(r):
    b, p = make_breaker(r), name()
    await b.on_failure(p)
    await b.on_failure(p)
    assert await b.allow(p) == "allow"


async def test_threshold_failures_open_the_circuit(r):
    b, p = make_breaker(r), name()
    for _ in range(3):
        await b.on_failure(p)
    assert await b.allow(p) == "deny"


async def test_success_resets_failure_count(r):
    b, p = make_breaker(r), name()
    await b.on_failure(p)
    await b.on_failure(p)
    await b.on_success(p)  # 清账
    await b.on_failure(p)
    await b.on_failure(p)
    assert await b.allow(p) == "allow"  # 从未"连续"达到 3 次


async def test_half_open_grants_exactly_one_probe(r):
    b, p = make_breaker(r), name()
    for _ in range(3):
        await b.on_failure(p)
    await asyncio.sleep(1.1)  # 等 open 的 TTL 自然过期 → 半开
    assert await b.allow(p) == "probe"  # 第一个到的抢到探测令牌
    assert await b.allow(p) == "deny"  # 模拟另一个副本：拿不到令牌，继续拒


async def test_probe_failure_reopens_immediately(r):
    b, p = make_breaker(r), name()
    for _ in range(3):
        await b.on_failure(p)
    await asyncio.sleep(1.1)
    assert await b.allow(p) == "probe"
    await b.on_failure(p)  # 探测失败
    assert await b.allow(p) == "deny"  # 不必重新数 3 次，立刻回到 open


async def test_probe_success_closes_fully(r):
    b, p = make_breaker(r), name()
    for _ in range(3):
        await b.on_failure(p)
    await asyncio.sleep(1.1)
    assert await b.allow(p) == "probe"
    await b.on_success(p)  # 探测成功
    assert await b.allow(p) == "allow"  # 彻底闭合，账本清零


async def test_providers_are_independent(r):
    b, p1, p2 = make_breaker(r), name(), name()
    for _ in range(3):
        await b.on_failure(p1)
    assert await b.allow(p1) == "deny"
    assert await b.allow(p2) == "allow"  # 百炼挂了不该连累 Anthropic

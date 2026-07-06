import asyncio
import uuid

import redis.asyncio as aioredis

from aegis.gateway.breaker import CircuitBreaker


def name() -> str:
    return f"prov-{uuid.uuid4().hex[:8]}"  # 每个测试独立命名空间，互不污染


def make_breaker(r: aioredis.Redis, **kw) -> CircuitBreaker:
    kw.setdefault("failure_threshold", 3)
    kw.setdefault("open_seconds", 1)
    kw.setdefault("probe_ttl", 5)
    return CircuitBreaker(r, **kw)


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


# ---------- 审计加固 C ----------


async def test_probe_token_ttl_guarantees_self_healing(r):
    # SET NX 的 ex= 参数是"探针进程崩溃后系统自愈"的唯一保障——钉死它
    b, p = make_breaker(r, probe_ttl=1), name()
    for _ in range(3):
        await b.on_failure(p)
    await asyncio.sleep(1.1)  # open 过期 → 半开
    assert await b.allow(p) == "probe"
    ttl = await r.ttl(f"aegis:cb:{p}:probe")
    assert 0 < ttl <= 1  # ex 被正确设置
    await asyncio.sleep(1.1)  # 模拟探针进程崩溃：无人裁决，令牌自然过期
    assert await b.allow(p) == "probe"  # 系统放出下一个探针，而不是永久 deny


async def test_release_probe_frees_token_immediately(r):
    b, p = make_breaker(r), name()
    for _ in range(3):
        await b.on_failure(p)
    await asyncio.sleep(1.1)
    assert await b.allow(p) == "probe"
    await b.release_probe(p)  # 探针没打出去（如被限流拦下）→ 主动归还
    assert await b.allow(p) == "probe"  # 立刻可再领，不用干等 probe_ttl


# ---------- M1.12a Redis 降级 ----------


async def test_degraded_breaker_fails_open_then_counts_locally(dead_r):
    b, p = CircuitBreaker(dead_r, failure_threshold=2, open_seconds=1), name()
    assert await b.allow(p) == "allow"  # fail-open 基调：Redis 挂≠上游挂
    await b.on_failure(p)
    await b.on_failure(p)
    assert await b.allow(p) == "deny"  # 但单机自保仍在：本地计数到阈值照样熔断
    await asyncio.sleep(1.1)
    assert await b.allow(p) == "probe"  # 本地版半开
    await b.on_success(p)
    assert await b.allow(p) == "allow"  # 成功清账，彻底闭合

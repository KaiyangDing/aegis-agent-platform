import asyncio
import os
import uuid

import pytest
import redis.asyncio as aioredis

from aegis.gateway.ratelimit import RateLimiter

TEST_REDIS_URL = os.environ.get("AEGIS_TEST_REDIS_URL", "redis://localhost:6379/9")


@pytest.fixture
async def r():
    client = aioredis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        if os.environ.get("CI"):
            raise
        pytest.skip("本地 Redis 未启动：docker compose -f deploy/docker-compose.yml up -d")
    yield client
    await client.aclose()


def scope() -> str:
    return f"test:{uuid.uuid4().hex[:8]}"


async def test_burst_up_to_capacity_then_denied(r):
    rl, s = RateLimiter(r), scope()
    results = [await rl.try_take(s, rate=1, capacity=5) for _ in range(6)]
    assert [ok for ok, _ in results] == [True] * 5 + [False]  # 满桶突发 5 个，第 6 个拒


async def test_denied_comes_with_wait_hint(r):
    rl, s = RateLimiter(r), scope()
    for _ in range(3):
        await rl.try_take(s, rate=1, capacity=3)
    ok, wait = await rl.try_take(s, rate=1, capacity=3)
    assert not ok
    assert 0 < wait <= 1.05  # 差 1 个令牌、速率 1/s → 建议等约 1 秒


async def test_tokens_refill_over_time(r):
    rl, s = RateLimiter(r), scope()
    for _ in range(3):
        await rl.try_take(s, rate=10, capacity=3)
    ok, _ = await rl.try_take(s, rate=10, capacity=3)
    assert not ok
    await asyncio.sleep(0.15)  # rate=10/s → 0.15s 补回约 1.5 个
    ok, _ = await rl.try_take(s, rate=10, capacity=3)
    assert ok


async def test_refill_never_exceeds_capacity(r):
    rl, s = RateLimiter(r), scope()
    await rl.try_take(s, rate=100, capacity=2)  # 建桶
    await asyncio.sleep(0.3)  # 理论补给 30 个，但桶只装 2 个
    results = [await rl.try_take(s, rate=100, capacity=2) for _ in range(3)]
    oks = [ok for ok, _ in results]
    assert oks[0] and not all(oks)  # 有令牌可拿，但绝没有 3 个——封顶生效


async def test_scopes_are_independent(r):
    rl, s1, s2 = RateLimiter(r), scope(), scope()
    for _ in range(3):
        await rl.try_take(s1, rate=1, capacity=3)
    ok1, _ = await rl.try_take(s1, rate=1, capacity=3)
    ok2, _ = await rl.try_take(s2, rate=1, capacity=3)
    assert not ok1
    assert ok2  # 租户 A 花光配额不该连累租户 B


async def test_wait_take_queues_briefly_then_succeeds(r):
    rl, s = RateLimiter(r), scope()
    for _ in range(2):
        await rl.try_take(s, rate=10, capacity=2)
    assert await rl.wait_take(s, rate=10, capacity=2, max_wait=1.0)  # 排队约 0.1s 后拿到


async def test_wait_take_gives_up_beyond_budget(r):
    rl, s = RateLimiter(r), scope()
    await rl.try_take(s, rate=0.1, capacity=1)  # 下一个令牌要 10 秒后
    assert not await rl.wait_take(s, rate=0.1, capacity=1, max_wait=0.2)  # 预算不够，果断放弃

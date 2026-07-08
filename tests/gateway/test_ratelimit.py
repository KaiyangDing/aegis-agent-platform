import asyncio
import uuid
from typing import cast

import redis.asyncio as aioredis

from aegis.gateway.ratelimit import RateLimiter


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
    # 时序参数放宽（审计加固 C）：rate=2 → "不该有令牌"的判定窗口 500ms，
    # 共享 CI runner 的调度停顿不再能翻车（原 rate=10 只有 100ms 余量）
    rl, s = RateLimiter(r), scope()
    for _ in range(3):
        await rl.try_take(s, rate=2, capacity=3)
    ok, _ = await rl.try_take(s, rate=2, capacity=3)
    assert not ok
    await asyncio.sleep(0.8)  # rate=2/s → 补回约 1.6 个，上下都有余量
    ok, _ = await rl.try_take(s, rate=2, capacity=3)
    assert ok


async def test_refill_never_exceeds_capacity(r):
    # 同上放宽：rate=2 时第三次取令牌的失败窗口为 500ms（原 rate=100 仅 10ms，必然偶发红）
    rl, s = RateLimiter(r), scope()
    await rl.try_take(s, rate=2, capacity=2)  # 建桶并取走 1 个
    await asyncio.sleep(1.0)  # 理论补给 2 个，但桶封顶 2 个
    results = [await rl.try_take(s, rate=2, capacity=2) for _ in range(3)]
    assert [ok for ok, _ in results] == [True, True, False]  # 封顶生效，且断言更精确


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


# ---------- M1.12a Redis 降级 ----------


async def test_degraded_local_bucket_still_enforces(dead_r):
    rl, s = RateLimiter(dead_r, replicas=1), scope()
    results = [await rl.try_take(s, rate=1, capacity=5) for _ in range(6)]
    assert [ok for ok, _ in results] == [True] * 5 + [False]  # 降级了，但限流语义还在


async def test_degraded_quota_divided_by_replicas(dead_r):
    rl, s = RateLimiter(dead_r, replicas=2), scope()  # 两副本：本地只拿全局的一半
    results = [await rl.try_take(s, rate=1, capacity=4) for _ in range(3)]
    assert [ok for ok, _ in results] == [True, True, False]  # capacity 4/2=2


# ---------- 复盘补丁二：降级粘滞 + 顺路探针 ----------


class _FlakyScript:
    """可开关的假 Lua 脚本：先挂后好，模拟 Redis 从故障到恢复的完整周期。"""

    def __init__(self) -> None:
        self.fail = True
        self.calls = 0

    async def __call__(self, keys: list, args: list) -> list:
        self.calls += 1
        if self.fail:
            raise ConnectionError("redis down")
        return [1, "0"]


class _FakeRedis:
    """只鸭子实现 RateLimiter 用到的 register_script；cast 只为过 mypy。"""

    def __init__(self) -> None:
        self.script = _FlakyScript()

    def register_script(self, lua: str) -> _FlakyScript:
        return self.script


def _flaky_limiter(probe_interval: float) -> tuple[RateLimiter, _FlakyScript]:
    fake = _FakeRedis()
    rl = RateLimiter(cast(aioredis.Redis, fake), probe_interval=probe_interval)
    return rl, fake.script


async def test_degraded_is_sticky_not_hammering_redis():
    rl, script = _flaky_limiter(probe_interval=60.0)
    s = scope()
    for _ in range(6):
        await rl.try_take(s, rate=50, capacity=25)
    assert script.calls == 1  # 只有首次撞了 Redis；降级期内不再每次支付连接失败延迟


async def test_probe_recovers_and_switches_back():
    rl, script = _flaky_limiter(probe_interval=0.3)
    s = scope()
    await rl.try_take(s, rate=50, capacity=25)  # 首次失败 → 降级
    script.fail = False  # Redis"复活"
    await asyncio.sleep(0.35)  # 越过探测窗
    ok, _ = await rl.try_take(s, rate=50, capacity=25)
    assert ok and script.calls == 2  # 这次是探针：打到 Redis 并拿到共享桶裁决
    await rl.try_take(s, rate=50, capacity=25)
    assert script.calls == 3  # 已切回共享桶：之后每次都走 Redis


async def test_failed_probe_stays_degraded_and_reschedules():
    rl, script = _flaky_limiter(probe_interval=0.3)
    s = scope()
    await rl.try_take(s, rate=50, capacity=25)  # 降级
    await asyncio.sleep(0.35)
    ok, _ = await rl.try_take(s, rate=50, capacity=25)  # 探针出击，仍失败
    assert ok and script.calls == 2  # 裁决由本地桶兜底，请求没有被故障拖死
    await rl.try_take(s, rate=50, capacity=25)  # 下一个探测窗未到
    assert script.calls == 2  # 失败探针把窗口顺延——不连环撞

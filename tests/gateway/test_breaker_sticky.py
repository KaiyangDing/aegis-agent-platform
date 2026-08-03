"""M4.0④（#29）：熔断器 Redis 触点的降级粘滞化——复盘补丁二同款范式。

病灶（00 §10.1 #29）：`_degraded` 此前**只用于日志去重**，不 gate Redis 调用——
降级期内每次 `allow`/`on_success`/`on_failure`/`release_probe` 照撞 Redis，
每请求至少 2 次触点（allow + on_success/on_failure），每次白付一遍连接失败延迟
（客户端快速失败后为 connect 1s ~ read 2s 级）。M5.2 要压 3 档并发多副本，
这笔开销会直接污染 P50/P99——"缓存与计量故障绝不拖垮请求"（00 §2.2）在熔断这条
路径上此前只兑现了一半（不抛异常 ✅、不付延迟 ❌）。

修法与 `RateLimiter`（ratelimit.py:86-115）、`FailoverSessionLock`（locks.py:221-250）
同构：降级粘滞 + 每 probe_interval 秒一个顺路探针。**探针只在 `allow` 领**——
它是每请求必过的判定入口且有本地兜底；其余三个触点在降级期直接走本地镜像，
不各自领探针（否则四个窗口互相续期，恢复时机变得不可预测）。
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import redis.asyncio as aioredis

from aegis.gateway.breaker import CircuitBreaker


class _FlakyRedis:
    """可开关的假 Redis：只鸭子实现 CircuitBreaker 用到的五个方法，逐次记账。"""

    def __init__(self) -> None:
        self.fail = True
        self.calls = 0

    def _hit(self) -> None:
        self.calls += 1
        if self.fail:
            raise ConnectionError("redis down")

    async def exists(self, *keys: str) -> int:
        self._hit()
        return 0

    async def get(self, key: str) -> str | None:
        self._hit()
        return None

    async def set(self, key: str, value: str, **kw: Any) -> bool:
        self._hit()
        return True

    async def delete(self, *keys: str) -> int:
        self._hit()
        return len(keys)

    async def incr(self, key: str) -> int:
        self._hit()
        return 1

    async def expire(self, key: str, seconds: int) -> bool:
        self._hit()
        return True


def _flaky_breaker(probe_interval: float) -> tuple[CircuitBreaker, _FlakyRedis]:
    fake = _FlakyRedis()
    cb = CircuitBreaker(cast(aioredis.Redis, fake), probe_interval=probe_interval)
    return cb, fake


async def test_degraded_allow_is_sticky_not_hammering_redis() -> None:
    """降级后 `allow` 不再每次撞 Redis——只有首次那一撞，其余走本地镜像。"""
    cb, fake = _flaky_breaker(probe_interval=60.0)
    for _ in range(6):
        assert await cb.allow("p1") == "allow"  # 本地兜底：无失败账 → 放行（fail-open 基调）
    assert fake.calls == 1


async def test_degraded_write_touchpoints_skip_redis() -> None:
    """三个非判定触点在降级期同样跳过 Redis，但**本地记账照旧**——
    降级的是"共享状态"，不是"熔断能力"：本地 fails 攒够仍要 deny。"""
    cb, fake = _flaky_breaker(probe_interval=60.0)
    await cb.allow("p2")  # 首撞 → 降级
    baseline = fake.calls
    for _ in range(5):  # failure_threshold 缺省 5
        await cb.on_failure("p2")
    await cb.on_success("p3")
    await cb.release_probe("p2")
    assert fake.calls == baseline  # 降级期零 Redis 调用
    assert await cb.allow("p2") == "deny"  # 本地记账生效：攒满即开断路
    assert fake.calls == baseline  # 这次 allow 也没撞（窗口未到）


async def test_probe_recovers_and_switches_back() -> None:
    """探针成功即切回集体记忆：此后每次 allow 都走 Redis。"""
    cb, fake = _flaky_breaker(probe_interval=0.3)
    await cb.allow("p4")  # 降级
    fake.fail = False  # Redis 复活
    await asyncio.sleep(0.35)
    assert await cb.allow("p4") == "allow"
    assert fake.calls == 3  # 探针：exists + get（两次调用打到 Redis）
    await cb.allow("p4")
    assert fake.calls == 5  # 已切回：继续走 Redis


async def test_failed_probe_stays_degraded_and_reschedules() -> None:
    """探针失败→窗口顺延，不连环撞：故障期的调用成本恒定，与 QPS 无关。"""
    cb, fake = _flaky_breaker(probe_interval=0.3)
    await cb.allow("p5")
    assert fake.calls == 1
    await asyncio.sleep(0.35)
    assert await cb.allow("p5") == "allow"  # 探针出击仍失败，本地兜底照常给裁决
    assert fake.calls == 2
    await cb.allow("p5")
    await cb.allow("p5")
    assert fake.calls == 2  # 下一个窗口未到——绝不连撞


async def test_degradation_preserves_fail_open_semantics() -> None:
    """粘滞化**不改变降级语义本身**（ADR-005 降级契约）：只改"降级期还撞不撞 Redis"。

    无失败账时放行（fail-open 基调），这条在粘滞前后必须一模一样。
    """
    cb, _ = _flaky_breaker(probe_interval=60.0)
    assert await cb.allow("p6") == "allow"
    for _ in range(5):
        await cb.on_failure("p6")
    assert await cb.allow("p6") == "deny"  # 攒满即断
    await cb.on_success("p6")  # 成功清账（本地）
    assert await cb.allow("p6") == "allow"

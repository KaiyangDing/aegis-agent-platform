"""M4.0④（#29）：精确缓存 Redis 触点的降级粘滞化——熔断侧同款，落点在 router。

**为什么修在 router 而不是 `ExactCache`**（拍板：粘滞访问器放调用侧，保持原分工）：
`ExactCache` 自身**零异常处理**（cache.py 全文无 except Redis 错误），降级语义一直住在
调用方 `router.complete`（router.py:217-222 读→miss / :316-320 写→skip）。把粘滞塞进
`ExactCache` 会让"缓存故障怎么办"分裂到两处；留在 router 则一处说了算，且 `ExactCache`
继续保持"纯存取、不谈降级"的单一职责。

病灶与熔断同源：降级只做到"不抛异常"，没做到"不付延迟"——每请求 get 必撞、
未命中且成功时 put 再撞，故障期每次白付一遍连接失败延迟。00 §2.2「缓存与计量故障
绝不拖垮请求」在此前只兑现了一半。
"""

from __future__ import annotations

import asyncio

from aegis.gateway.router import Candidate, GatewayLimits, LLMGateway
from aegis.gateway.schema import LLMChunk, LLMRequest, Message, StopChunk, TextDelta, UsageChunk

OK_CHUNKS: list[LLMChunk] = [
    TextDelta(text="ok"),
    UsageChunk(model="m", prompt_tokens=1, completion_tokens=1),
    StopChunk(reason="end_turn"),
]


# 夹具自带而非从 test_router import：tests/ 无 __init__.py（pytest rootdir 直挂），
# 跨测试模块的相对 import 不成立——与"测试模块名须全仓唯一"（M3.9 偏差 48）同源约束。
class _OkProvider:
    def __init__(self, name: str = "p1") -> None:
        self.name = name
        self.calls = 0

    async def complete(self, req, model):
        self.calls += 1
        for c in OK_CHUNKS:
            yield c


class _AllowBreaker:
    async def allow(self, provider: str) -> str:
        return "allow"

    async def on_success(self, provider: str) -> None: ...

    async def on_failure(self, provider: str) -> None: ...

    async def release_probe(self, provider: str) -> None: ...


class _OpenLimiter:
    async def wait_take(self, scope, rate, capacity, *, max_wait=10.0, cost=1.0) -> bool:
        return True


class _FlakyCache:
    """可开关的假缓存：get/put 逐次记账，fail 时抛连接错（形状同 redis-py）。"""

    def __init__(self) -> None:
        self.fail = True
        self.gets = 0
        self.puts = 0

    async def get(self, req: LLMRequest) -> list[LLMChunk] | None:
        self.gets += 1
        if self.fail:
            raise ConnectionError("redis down")
        return None  # 恢复后一律 miss：本文件只测触点次数，命中路径归 test_router

    async def put(self, req: LLMRequest, chunks: list[LLMChunk]) -> None:
        self.puts += 1
        if self.fail:
            raise ConnectionError("redis down")


def _req() -> LLMRequest:
    return LLMRequest(tier="fast", tenant_id="t-cache", messages=[Message(role="user", content="x")])


async def _run(gw) -> list:
    return [c async for c in gw.complete(_req())]


def _gw_with_cache(cache: _FlakyCache, probe_interval: float) -> LLMGateway:
    provider = _OkProvider()
    return LLMGateway(
        providers={provider.name: provider},
        routes={"fast": [Candidate(provider.name, "model-p1")]},
        breaker=_AllowBreaker(),
        limiter=_OpenLimiter(),
        cache=cache,
        limits=GatewayLimits(max_wait=0.1),
        cache_probe_interval=probe_interval,
    )


async def test_degraded_cache_is_sticky_not_hammering_redis() -> None:
    """降级后不再每请求撞缓存：首次 get 失败即粘滞，其后 get/put 全部跳过。"""
    cache = _FlakyCache()
    gw = _gw_with_cache(cache, probe_interval=60.0)
    for _ in range(5):
        assert await _run(gw) == OK_CHUNKS  # 请求照常成功——降级不拖垮主链路
    assert cache.gets == 1  # 只有首撞
    assert cache.puts == 0  # 读侧已降级，写侧同窗跳过（不各自领探针）


async def test_probe_recovers_and_switches_back() -> None:
    """探针成功即切回：此后 get 与 put 都恢复。"""
    cache = _FlakyCache()
    gw = _gw_with_cache(cache, probe_interval=0.3)
    await _run(gw)  # 降级
    cache.fail = False
    await asyncio.sleep(0.35)
    await _run(gw)  # 探针 get 成功 → 切回；同请求的 put 照常
    assert (cache.gets, cache.puts) == (2, 1)
    await _run(gw)
    assert (cache.gets, cache.puts) == (3, 2)  # 已恢复常态


async def test_failed_probe_stays_degraded_and_reschedules() -> None:
    """探针失败→窗口顺延：故障期缓存触点成本恒定，与 QPS 无关。"""
    cache = _FlakyCache()
    gw = _gw_with_cache(cache, probe_interval=0.3)
    await _run(gw)
    assert cache.gets == 1
    await asyncio.sleep(0.35)
    await _run(gw)  # 探针出击仍失败
    assert cache.gets == 2
    await _run(gw)
    await _run(gw)
    assert cache.gets == 2  # 窗口未到，绝不连撞


async def test_cache_failure_never_breaks_the_request() -> None:
    """降级语义本身不变（ADR-005）：缓存全程故障，请求仍拿到完整正常结果。"""
    cache = _FlakyCache()
    gw = _gw_with_cache(cache, probe_interval=60.0)
    assert await _run(gw) == OK_CHUNKS
    assert await _run(gw) == OK_CHUNKS

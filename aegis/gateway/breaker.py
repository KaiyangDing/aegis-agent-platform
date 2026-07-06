"""熔断器：供应商级的"别再撞了"开关，状态共享在 Redis（多副本一致）。

状态建模（每个 provider 三把 key，TTL 即状态迁移，无后台任务）：
- aegis:cb:{p}:open   存在 = open 状态；TTL 过期自动进入"半开机会"
- aegis:cb:{p}:fails  连续失败计数；成功清零；自带窗口 TTL
- aegis:cb:{p}:probe  半开探测令牌；SET NX 保证全集群只有一个探针

计账规则：只有 5xx/超时算熔断失败——429 是限流的领地（上游活着，我们太快），
Auth/BadRequest 是我们自己的问题，供应商无辜。

原子性分析（为什么不需要 Lua）：INCR 自身原子；重复 SET open 幂等；
探测互斥靠 SET NX。需要 Lua 的读-改-写捆绑在限流器（M1.8）。
"""

from typing import Literal

import redis.asyncio as aioredis

Decision = Literal["allow", "probe", "deny"]


class CircuitBreaker:
    def __init__(
        self,
        redis: aioredis.Redis,
        *,
        failure_threshold: int = 5,
        open_seconds: int = 30,
        probe_ttl: int = 120,  # 必须 ≥ 读超时 90s：探针飞行中令牌过期会放出第二个并发探针
        fail_window: int = 120,
    ):
        self._r = redis
        self._threshold = failure_threshold
        self._open_seconds = open_seconds
        self._probe_ttl = probe_ttl
        self._fail_window = fail_window

    def _keys(self, provider: str) -> tuple[str, str, str]:
        base = f"aegis:cb:{provider}"
        return f"{base}:open", f"{base}:fails", f"{base}:probe"

    async def allow(self, provider: str) -> Decision:
        """请求放行判定：allow=正常 / probe=你是唯一探针 / deny=快速拒绝。"""
        open_key, fails_key, probe_key = self._keys(provider)
        if await self._r.exists(open_key):
            return "deny"
        fails = int(await self._r.get(fails_key) or 0)
        if fails < self._threshold:
            return "allow"
        # open 已过期但失败账未清 → 半开：SET NX 抢全集群唯一的探测令牌
        won = await self._r.set(probe_key, "1", nx=True, ex=self._probe_ttl)
        return "probe" if won else "deny"

    async def on_success(self, provider: str) -> None:
        """成功 = 彻底闭合：三把 key 一并清掉。"""
        await self._r.delete(*self._keys(provider))

    async def release_probe(self, provider: str) -> None:
        """归还未获裁决的探测令牌——探针没打出去（被限流拦下）或结果不构成
        熔断裁决（429/Auth 类失败）时调用，否则令牌滞留 probe_ttl 秒拖慢恢复。

        无 owner-token 校验（已知取舍）：极端时序下可能误删其他副本刚领的
        新令牌，代价只是多放一个探针、可自愈；owner CAD 在此属过度设计。
        """
        await self._r.delete(self._keys(provider)[2])

    async def on_failure(self, provider: str) -> None:
        open_key, fails_key, probe_key = self._keys(provider)
        fails = await self._r.incr(fails_key)
        await self._r.expire(fails_key, self._fail_window)
        if fails >= self._threshold:
            await self._r.set(open_key, "1", ex=self._open_seconds)
            await self._r.delete(probe_key)  # 探测失败的场景：令牌作废，重新计时

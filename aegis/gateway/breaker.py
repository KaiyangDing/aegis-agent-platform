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

import logging
import time
from dataclasses import dataclass, field
from typing import Literal

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

Decision = Literal["allow", "probe", "deny"]


@dataclass
class _LocalState:
    """降级形态的单机记忆：失去 Redis 集体记忆后各副本各自为政（自保而非全集群一致）。

    三键状态机的进程内完整镜像（2026-07-08 复盘升级）：fails/open_until/probe_until
    ↔ fails/open/probe 三把 key。四个镜像点各有单测钉死。
    """

    fails: int = 0
    open_until: float = field(default=0.0)
    probe_until: float = field(default=0.0)  # 本地探测令牌：主路径 SET NX 的进程内镜像


class CircuitBreaker:
    def __init__(
        self,
        redis: aioredis.Redis,
        *,
        failure_threshold: int = 5,
        open_seconds: int = 30,
        probe_ttl: int = 120,  # 下界=失败裁决最坏耗时(限流排队10+connect5+首块25≈40s)×3 余量，
        #                        C1 改造后旧口径"≥读超时90s"已失效；上界=丢探针的额外锁死时间
        #                        （实际被 fail_window 封顶：fails 过期会让半开自动溶解为闭合）
        fail_window: int = 120,
    ):
        self._r = redis
        self._threshold = failure_threshold
        self._open_seconds = open_seconds
        self._probe_ttl = probe_ttl
        self._fail_window = fail_window
        self._local: dict[str, _LocalState] = {}
        self._degraded = False

    def _keys(self, provider: str) -> tuple[str, str, str]:
        base = f"aegis:cb:{provider}"
        return f"{base}:open", f"{base}:fails", f"{base}:probe"

    async def allow(self, provider: str) -> Decision:
        try:
            decision = await self._allow_redis(provider)
        except Exception:
            self._note_degraded()
            return self._local_allow(provider)
        if self._degraded:
            logger.warning("Redis 熔断状态恢复，切回集体记忆")
            self._degraded = False
        return decision

    async def _allow_redis(self, provider: str) -> Decision:
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

    def _local_allow(self, provider: str) -> Decision:
        st = self._local.setdefault(provider, _LocalState())
        now = time.monotonic()
        if st.open_until > now:
            return "deny"
        if st.fails >= self._threshold:
            # 半开与主路径同构：令牌互斥只放一个探针、其余 deny（堵挂起场景下
            # 探针飞行 25s 的并发泄漏窗）；fails 不动——探测失败 +1 后仍≥阈值，
            # 立即重开（不变量：test_probe_failure_reopens_immediately 的降级镜像）
            if st.probe_until > now:
                return "deny"
            st.probe_until = now + self._probe_ttl
            return "probe"
        return "allow"

    async def on_success(self, provider: str) -> None:
        """成功 = 彻底闭合：三把 key 一并清掉。"""
        self._local.pop(provider, None)
        try:
            await self._r.delete(*self._keys(provider))
        except Exception:
            self._note_degraded()

    async def on_failure(self, provider: str) -> None:
        st = self._local.setdefault(provider, _LocalState())
        st.fails += 1
        if st.fails >= self._threshold:
            st.open_until = time.monotonic() + self._open_seconds
            # 镜像 _on_failure_redis 的 delete(probe_key)：令牌作废——
            # 否则重开(30s)后被残留令牌(120s)再多锁 90s
            st.probe_until = 0.0
        try:
            await self._on_failure_redis(provider)
        except Exception:
            self._note_degraded()

    async def _on_failure_redis(self, provider: str) -> None:
        open_key, fails_key, probe_key = self._keys(provider)
        fails = await self._r.incr(fails_key)
        await self._r.expire(fails_key, self._fail_window)
        if fails >= self._threshold:
            await self._r.set(open_key, "1", ex=self._open_seconds)
            await self._r.delete(probe_key)  # 探测失败的场景：令牌作废，重新计时

    async def release_probe(self, provider: str) -> None:
        """归还未获裁决的探测令牌——探针没打出去或结果不构成裁决时调用。

        无 owner-token 校验（已知取舍）：极端时序下可能误删其他副本刚领的
        新令牌，代价只是多放一个探针、可自愈；owner CAD 在此属过度设计。
        本地令牌同步归还（完整镜像后本地也有令牌概念——2026-07-08 复盘升级）。
        """
        st = self._local.get(provider)
        if st is not None:
            st.probe_until = 0.0
        try:
            await self._r.delete(self._keys(provider)[2])
        except Exception:
            self._note_degraded()

    def _note_degraded(self) -> None:
        if not self._degraded:
            logger.warning(
                "Redis 熔断状态不可用，降级为本地计数（fail-open 基调；"
                "'全集群唯一探针'等承诺在降级期间失效）",
                exc_info=True,
            )
            self._degraded = True

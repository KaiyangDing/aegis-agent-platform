"""出站限流：Redis 令牌桶（Lua 原子执行，多副本共享）。

为什么必须 Lua：取令牌是"读桶→按时间补给→扣减→写回"的读-改-写序列，
没有单条 Redis 命令能表达补给逻辑，两个副本交错执行会超发令牌。
Lua 脚本在 Redis 单线程内整体执行，等于一条自定义的原子命令。

时钟：用 redis.call('TIME')（服务器钟）而非各副本本地钟——副本时钟会漂移。
返回值：RESP 协议把浮点截断为整数，"还需等待秒数"必须 tostring 后返回。

降级（M1.12，2026-07-08 复盘补丁二）：Redis 不可用时切进程内本地桶（配额=全局/副本数），
且降级是粘滞的——每 probe_interval 秒只放一个"顺路探针"借真实请求试探恢复，
其余请求直走本地桶，不为挂掉的依赖反复支付连接失败延迟（口径：故障绝不拖垮请求）。
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_sleep = asyncio.sleep  # 测试接缝，与 resilience 同款


@dataclass
class _LocalBucket:
    """降级形态的桶：Lua 脚本里那套算法的 Python 直译（对照着读）。"""

    tokens: float
    ts: float


_TOKEN_BUCKET_LUA = """
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])

local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1e6

local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity          -- 新桶开局满桶：允许合理的冷启动突发
  ts = now
end

local elapsed = math.max(0, now - ts)   -- Redis 主机时钟被 NTP 回拨时不做负补给
tokens = math.min(capacity, tokens + elapsed * rate)   -- 按流逝时间补给，封顶

local allowed = 0
local wait = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  wait = (cost - tokens) / rate    -- 还差的令牌 ÷ 速率 = 最早何时够
end

redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
-- 闲置桶自动回收；min 封顶防 rate 误配成极小值时 TTL 溢出 EXPIRE 参数范围
redis.call('EXPIRE', KEYS[1], math.min(math.ceil(capacity / rate) + 60, 86400))
return {allowed, tostring(wait)}
"""


class RateLimiter:
    def __init__(
        self,
        redis: aioredis.Redis,
        *,
        replicas: int = 1,
        probe_interval: float = 5.0,
    ):
        self._r = redis
        self._take = redis.register_script(_TOKEN_BUCKET_LUA)
        self._replicas = max(1, replicas)
        self._local: dict[str, _LocalBucket] = {}
        self._degraded = False
        self._probe_interval = probe_interval
        self._next_probe = 0.0  # monotonic 时刻：降级期内下一次允许探测 Redis 的时间

    async def try_take(
        self, scope: str, rate: float, capacity: float, cost: float = 1.0
    ) -> tuple[bool, float]:
        """立即尝试取令牌。Redis 不可用时降级为进程内桶（配额=全局/副本数）。

        降级是粘滞的：降级期内不再每次调用都撞 Redis（连接失败在 redis-py 8
        默认退避下一次拖数秒，会把"绝不拖垮请求"变成空话），每 probe_interval
        秒放一个顺路探针试探恢复——与熔断器半开的本地探测令牌同构。
        """
        if self._degraded:
            now = time.monotonic()
            if now < self._next_probe:
                return self._local_take(
                    scope, rate / self._replicas, capacity / self._replicas, cost
                )
            self._next_probe = now + self._probe_interval  # 领探针：检查与写入之间
            #                     无 await，事件循环内天然互斥——并发者继续走本地桶
        try:
            allowed, wait = await self._take(
                keys=[f"aegis:rl:{scope}"], args=[rate, capacity, cost]
            )
        except Exception:
            if not self._degraded:
                logger.warning(
                    "Redis 限流不可用，降级为进程内令牌桶（本地配额=全局/%d）",
                    self._replicas,
                    exc_info=True,
                )
                self._degraded = True
                self._next_probe = time.monotonic() + self._probe_interval
            return self._local_take(scope, rate / self._replicas, capacity / self._replicas, cost)
        if self._degraded:
            logger.warning("Redis 限流恢复，切回共享令牌桶")
            self._degraded = False
            self._local.clear()  # 旧桶作废：下次再降级时开局满桶，与 Lua 冷启动语义一致
        return bool(int(allowed)), float(wait)

    def _local_take(
        self, scope: str, rate: float, capacity: float, cost: float = 1.0
    ) -> tuple[bool, float]:
        now = time.monotonic()
        bucket = self._local.get(scope)
        if bucket is None:
            bucket = _LocalBucket(tokens=capacity, ts=now)
            self._local[scope] = bucket
        bucket.tokens = min(capacity, bucket.tokens + (now - bucket.ts) * rate)
        bucket.ts = now
        if bucket.tokens >= cost:
            bucket.tokens -= cost
            return True, 0.0
        return False, (cost - bucket.tokens) / rate if rate > 0 else 60.0

    async def wait_take(
        self,
        scope: str,
        rate: float,
        capacity: float,
        *,
        max_wait: float = 10.0,
        cost: float = 1.0,
    ) -> bool:
        """带等待的取令牌：出站限流的常用形态——短暂排队比直接失败体验好。

        在 max_wait 预算内循环"问一次、按提示睡一会"，超预算返回 False。
        """
        deadline = time.monotonic() + max_wait
        while True:
            ok, wait = await self.try_take(scope, rate, capacity, cost)
            if ok:
                return True
            if time.monotonic() + wait > deadline:
                return False
            await _sleep(max(wait, 0.01))  # 至少睡 10ms，避免空转刷 Redis

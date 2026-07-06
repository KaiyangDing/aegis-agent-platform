"""出站限流：Redis 令牌桶（Lua 原子执行，多副本共享）。

为什么必须 Lua：取令牌是"读桶→按时间补给→扣减→写回"的读-改-写序列，
没有单条 Redis 命令能表达补给逻辑，两个副本交错执行会超发令牌。
Lua 脚本在 Redis 单线程内整体执行，等于一条自定义的原子命令。

时钟：用 redis.call('TIME')（服务器钟）而非各副本本地钟——副本时钟会漂移。
返回值：RESP 协议把浮点截断为整数，"还需等待秒数"必须 tostring 后返回。
"""

import asyncio
import time

import redis.asyncio as aioredis

_sleep = asyncio.sleep  # 测试接缝，与 resilience 同款

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
    def __init__(self, redis: aioredis.Redis):
        self._r = redis
        # register_script：redis-py 先发 EVALSHA（按脚本哈希调缓存），
        # 未缓存时自动降级 EVAL 上传——脚本只传输一次，之后只传哈希
        self._take = redis.register_script(_TOKEN_BUCKET_LUA)

    async def try_take(
        self, scope: str, rate: float, capacity: float, cost: float = 1.0
    ) -> tuple[bool, float]:
        """立即尝试取令牌。返回 (是否拿到, 拿不到时建议等待的秒数)。"""
        allowed, wait = await self._take(keys=[f"aegis:rl:{scope}"], args=[rate, capacity, cost])
        return bool(int(allowed)), float(wait)

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

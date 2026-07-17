"""会话锁原语（ADR-005 角色 5）：SET NX + owner token + Lua CAD + 看门狗续期。

一把会话锁 = "同一会话同一时刻至多一个写者"的互斥承诺——EventWriter 单写者
前提（store.py:288）的接电位。Redis 主实现（交付①）；PG advisory 降级与粘滞
切换随交付②（C4：停 Redis 保住互斥而非放弃）。切换只发生在 acquire 边界，
持锁中途绝不换后端（跨后端互斥不可证——D13）；锁失效的最后防线是
events (session_id, seq) 唯一约束（物理兜底，store.py:97）。
消费者：M2.9 挂起-恢复单入口、M2.10 恢复调度、M3.2 会话互斥（锁被占 → 409）。
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Protocol

import redis.asyncio as aioredis


class SessionLockHeld(RuntimeError):
    """锁被占：上一条消息处理中 / 另一副本正在恢复。M3.2 捕获映射 409。"""


def new_owner_token() -> str:
    """每次持锁一个新 token（uuid4().hex）——释放/续期的身份凭证。

    不带 token 的裸 DEL 会误删他人的锁：A 的锁过期后 B 获取，A 迟到的
    release 不验身份就把 B 的锁删了（ADR-005 角色 5 原文）。
    """
    return uuid.uuid4().hex


class SessionLock(Protocol):
    """三方法形状 + owner token 语义（结构化协议，与 GatewayLike 同款惯例）。"""

    async def acquire(self, session_id: str, owner_token: str, *, ttl_s: float = 30.0) -> bool: ...

    async def extend(self, session_id: str, owner_token: str, *, ttl_s: float = 30.0) -> bool: ...

    async def release(self, session_id: str, owner_token: str) -> bool: ...


# CAD（compare-and-delete）：GET 比对与 DEL 必须原子——分两步发会在比对与删除
# 之间被"过期 + 他人获取"插队，退化回裸 DEL 误删（ADR-005 角色 5）
_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
else
  return 0
end
"""

# 比对续期：只有 owner 能续自己的锁；键已过期/易主则续期失败（丢锁可感知）
_EXTEND_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('PEXPIRE', KEYS[1], ARGV[2])
else
  return 0
end
"""


def _lock_key(session_id: str) -> str:
    """与 aegis:rl:{scope}（限流）、aegis:cb:{provider}（熔断）同族命名（D9）。"""
    return f"aegis:lock:session:{session_id}"


class RedisSessionLock:
    """Redis 主实现：SET NX 获取、Lua CAD 释放、Lua 比对续期。

    客户端一律走 get_redis() 共享单例（decode_responses=True——Lua 里 GET 与
    ARGV 比对 bytes vs str 不齐是 CAD 恒 False 的经典坑，m2.9 §7 坑 5）。
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._r = redis
        self._release = redis.register_script(_RELEASE_LUA)  # 注册范式同 ratelimit.py:79
        self._extend = redis.register_script(_EXTEND_LUA)

    async def acquire(self, session_id: str, owner_token: str, *, ttl_s: float = 30.0) -> bool:
        # px 必须是毫秒整数（float 会 DataError，§7 坑 6）；nx=True：被占时返回 None
        ok = await self._r.set(_lock_key(session_id), owner_token, nx=True, px=int(ttl_s * 1000))
        return bool(ok)

    async def extend(self, session_id: str, owner_token: str, *, ttl_s: float = 30.0) -> bool:
        result = await self._extend(keys=[_lock_key(session_id)], args=[owner_token, str(int(ttl_s * 1000))])
        return bool(int(result))

    async def release(self, session_id: str, owner_token: str) -> bool:
        result = await self._release(keys=[_lock_key(session_id)], args=[owner_token])
        return bool(int(result))


@dataclass
class HeldSessionLock:
    """一次持锁的凭据：token 是身份，lost 是看门狗的失锁信号（置位 = 持有者应尽快收尾）。"""

    session_id: str
    owner_token: str
    lost: asyncio.Event = field(default_factory=asyncio.Event)


@asynccontextmanager
async def hold_session_lock(
    lock: SessionLock,
    session_id: str,
    *,
    ttl_s: float = 30.0,
    renew_interval_s: float = 10.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AsyncIterator[HeldSessionLock]:
    """唯一推荐的持锁形态：获取 → 看门狗续期 → 退出释放。

    裸 acquire/release 只允许出现在锁自身的测试里。ttl=30s 配 10s 续期间隔，
    给两次续期失败留容错窗（D10）；看门狗续期失败或异常一律 lost.set() 后停止——
    不重试、不切后端（D13），丢锁后果由 (session_id, seq) 唯一约束物理兜底。
    sleep 可注入：看门狗测试不做真实计时断言（00 §2.2 测试纪律）。
    """
    token = new_owner_token()
    if not await lock.acquire(session_id, token, ttl_s=ttl_s):
        raise SessionLockHeld(f"会话 {session_id} 的锁被占用——上一条消息处理中或另一副本正在恢复")
    held = HeldSessionLock(session_id, token)

    async def _watchdog() -> None:
        while True:
            await sleep(renew_interval_s)
            try:
                renewed = await lock.extend(session_id, token, ttl_s=ttl_s)
            except Exception:  # 后端异常同样按丢锁处理：不猜测、不重试（CancelledError 不在此列）
                held.lost.set()
                return
            if not renewed:
                held.lost.set()
                return

    watchdog = asyncio.create_task(_watchdog())
    try:
        yield held
    finally:
        # 顺序固定：先停看门狗再释放——反过来看门狗可能在 release 后又续一轮，
        # CAD 虽会失败但时序噪音大（§7 坑 7）
        watchdog.cancel()
        try:
            await watchdog
        except asyncio.CancelledError:
            pass
        try:
            await lock.release(session_id, token)
        except Exception:
            pass  # Redis 挂了锁会自然过期；释放失败不掀翻业务收尾

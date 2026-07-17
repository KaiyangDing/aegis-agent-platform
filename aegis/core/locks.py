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
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Protocol

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aegis.core.db import get_engine
from aegis.core.redis import get_redis

logger = logging.getLogger(__name__)


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


class PgAdvisorySessionLock:
    """PG advisory 降级形态（评审 C4 修正三件套）。

    ① session 级 pg_try_advisory_lock——xact 级在首个事务提交即自动释放，
      撑不住跨多个事件写入事务的整个 run（§7 坑 2）；
    ② 专用 AUTOCOMMIT 连接持有、显式释放——advisory 锁跟 PG 会话（连接）走，
      带锁归池 = 锁寄生在池中连接上，重启才解（坑 3）；
    ③ hashtext(session_id) 在 PG 端算——Python hash() 每进程随机盐，
      两副本对同一会话算出不同键，互斥随机失效（坑 1）。
    TTL 语义：PG 会话级锁无 TTL，活性 = 连接活性（连接死亡锁自动释放，
    这也是崩溃兜底）；extend 仅确认仍持有。hashtext 是 int4：32 位碰撞的
    方向是多互斥不少互斥（两个会话偶然串行化，无安全损失）。
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._held: dict[str, tuple[str, AsyncConnection]] = {}  # session_id -> (owner_token, 专用连接)

    async def acquire(self, session_id: str, owner_token: str, *, ttl_s: float = 30.0) -> bool:
        if session_id in self._held:
            return False  # 同进程重复获取拒绝：advisory 本身可重入，这里与 SET NX 语义对齐
        conn = await self._engine.connect()
        # AUTOCOMMIT：会话级锁与事务无关，不开事务防连接挂在 "idle in transaction"
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        got = (
            await conn.execute(text("SELECT pg_try_advisory_lock(hashtext(:sid))"), {"sid": session_id})
        ).scalar_one()
        if not got:
            await conn.close()  # 没拿到锁的连接立即归还
            return False
        self._held[session_id] = (owner_token, conn)
        return True

    async def extend(self, session_id: str, owner_token: str, *, ttl_s: float = 30.0) -> bool:
        held = self._held.get(session_id)
        return held is not None and held[0] == owner_token  # 无 TTL 可续，只确认仍持有

    async def release(self, session_id: str, owner_token: str) -> bool:
        held = self._held.get(session_id)
        if held is None or held[0] != owner_token:
            return False  # owner 语义在应用层兜：advisory 锁认连接不认 token
        _, conn = held
        try:
            # 释放顺序（坑 3 正解）：同一条连接上显式 unlock → 此时归还才安全
            await conn.execute(text("SELECT pg_advisory_unlock(hashtext(:sid))"), {"sid": session_id})
            await conn.close()
        except Exception:
            # 最后保险：物理销毁连接——PG 会话死亡即释放其全部 advisory 锁；
            # 绝不允许带着锁归池
            await conn.invalidate()
        finally:
            del self._held[session_id]
        return True


class FailoverSessionLock:
    """Redis 主 + PG 降级的粘滞切换（与 ratelimit.py:93-115 已实装范式同构，D12）。

    降级期不再每次撞挂掉的 Redis（快速失败也有 ~1s 连接超时代价），每
    probe_interval_s 放一个顺路探针试探恢复。授予后端登记在 _granted，
    extend/release 按此路由——持锁中途绝不切后端（D13：跨后端互斥不可证；
    残余窗口由 events (session_id, seq) 唯一约束物理兜底）。
    锁占用（False）是常规结果不是故障，绝不触发降级。
    """

    def __init__(self, primary: SessionLock, fallback: SessionLock, *, probe_interval_s: float = 5.0) -> None:
        self._primary = primary
        self._fallback = fallback
        self._probe_interval_s = probe_interval_s
        self._granted: dict[str, SessionLock] = {}
        self._degraded = False
        self._next_probe = 0.0  # monotonic 时刻：降级期内下一次允许探测 primary 的时间

    async def acquire(self, session_id: str, owner_token: str, *, ttl_s: float = 30.0) -> bool:
        if self._degraded and time.monotonic() < self._next_probe:
            return await self._acquire_on(self._fallback, session_id, owner_token, ttl_s)
        if self._degraded:
            # 领探针：检查与写入之间无 await，事件循环内天然互斥——并发者继续走 fallback
            self._next_probe = time.monotonic() + self._probe_interval_s
        try:
            ok = await self._primary.acquire(session_id, owner_token, ttl_s=ttl_s)
        except Exception:
            if not self._degraded:
                logger.warning("会话锁 Redis 不可用，降级为 PG advisory lock（互斥语义保留）", exc_info=True)
                self._degraded = True
                self._next_probe = time.monotonic() + self._probe_interval_s
            return await self._acquire_on(self._fallback, session_id, owner_token, ttl_s)
        if self._degraded:
            logger.warning("会话锁 Redis 恢复，切回主后端")
            self._degraded = False
        if ok:
            self._granted[session_id] = self._primary
        return ok

    async def _acquire_on(self, backend: SessionLock, session_id: str, owner_token: str, ttl_s: float) -> bool:
        # fallback 也抛 → 原样上抛：Redis + PG 双灭 = 服务不可用（与 EventStoreUnavailable 同哲学，不吞）
        ok = await backend.acquire(session_id, owner_token, ttl_s=ttl_s)
        if ok:
            self._granted[session_id] = backend
        return ok

    async def extend(self, session_id: str, owner_token: str, *, ttl_s: float = 30.0) -> bool:
        backend = self._granted.get(session_id)
        if backend is None:
            return False
        return await backend.extend(session_id, owner_token, ttl_s=ttl_s)

    async def release(self, session_id: str, owner_token: str) -> bool:
        backend = self._granted.get(session_id)
        if backend is None:
            return False
        ok = await backend.release(session_id, owner_token)
        if ok:
            del self._granted[session_id]
        return ok


def build_session_lock() -> SessionLock:
    """组装在边缘（与 gateway/factory.py 同哲学）：Redis 主 + PG advisory 降级。

    仅供生产组装（M3.2 API 层）调用——get_redis()/get_engine() 是进程级单例，
    跨 event loop 不可复用，测试一律显式注入自建客户端/引擎的锁实例。
    """
    return FailoverSessionLock(RedisSessionLock(get_redis()), PgAdvisorySessionLock(get_engine()))

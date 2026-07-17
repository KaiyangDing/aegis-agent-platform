"""M2.9 交付①：会话锁 Redis 实现——NX 获取 / Lua CAD 释放 / 比对续期 / 看门狗。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from aegis.core.locks import (
    RedisSessionLock,
    SessionLockHeld,
    hold_session_lock,
    new_owner_token,
)

_SID = "lk-1"
_KEY = f"aegis:lock:session:{_SID}"


def _stepping_sleep(steps: int) -> tuple[list[float], Callable[[float], Awaitable[None]]]:
    """放行前 steps 次 sleep（记录时长立即返回），之后永久挂起等 cancel——看门狗跑固定轮数。"""
    calls: list[float] = []

    async def _sleep(delay: float) -> None:
        calls.append(delay)
        if len(calls) > steps:
            await asyncio.Event().wait()

    return calls, _sleep


class _StubLock:
    """协议形状的内存假锁：acquire/release 恒成功，extend 行为可配置（看门狗失败路径专用）。"""

    def __init__(self, *, extend_result: bool = True) -> None:
        self.extend_calls = 0
        self._extend_result = extend_result

    async def acquire(self, session_id: str, owner_token: str, *, ttl_s: float = 30.0) -> bool:
        return True

    async def extend(self, session_id: str, owner_token: str, *, ttl_s: float = 30.0) -> bool:
        self.extend_calls += 1
        return self._extend_result

    async def release(self, session_id: str, owner_token: str) -> bool:
        return True


async def test_acquire_sets_key_with_ttl(r) -> None:
    """获取成功：key=aegis:lock:session:{sid}、值=owner token、带 TTL。"""
    lock = RedisSessionLock(r)
    token = new_owner_token()
    assert await lock.acquire(_SID, token, ttl_s=30.0) is True
    assert await r.get(_KEY) == token
    assert await r.pttl(_KEY) > 0


async def test_second_acquire_different_owner_fails(r) -> None:
    """互斥核心：同会话第二个 owner 获取失败（SET NX 语义）。"""
    lock = RedisSessionLock(r)
    assert await lock.acquire(_SID, new_owner_token()) is True
    assert await lock.acquire(_SID, new_owner_token()) is False


async def test_release_with_wrong_token_is_noop(r) -> None:
    """CAD：错 token 释放是空操作——"不带 token 的 DEL 会误删他人锁"的反例钉死。"""
    lock = RedisSessionLock(r)
    token = new_owner_token()
    await lock.acquire(_SID, token)
    assert await lock.release(_SID, new_owner_token()) is False
    assert await r.get(_KEY) == token


async def test_release_with_owner_token_deletes(r) -> None:
    """对 token 释放：key 消失，随后他人可获取。"""
    lock = RedisSessionLock(r)
    token = new_owner_token()
    await lock.acquire(_SID, token)
    assert await lock.release(_SID, token) is True
    assert await r.get(_KEY) is None
    assert await lock.acquire(_SID, new_owner_token()) is True


async def test_extend_refreshes_ttl_only_for_owner(r) -> None:
    """比对续期：owner 续期 TTL 回满；错 token 续期失败且 TTL 不回满。"""
    lock = RedisSessionLock(r)
    token = new_owner_token()
    await lock.acquire(_SID, token, ttl_s=30.0)
    await r.pexpire(_KEY, 1000)  # 人工压低 TTL，让"回满"可观察（30s >> 1s，非计时断言）
    assert await lock.extend(_SID, token, ttl_s=30.0) is True
    assert await r.pttl(_KEY) > 1000
    before = await r.pttl(_KEY)
    assert await lock.extend(_SID, new_owner_token(), ttl_s=30.0) is False
    assert await r.pttl(_KEY) <= before


async def test_extend_after_expiry_returns_false(r) -> None:
    """键自然过期后续期失败——丢锁可感知（看门狗 lost 信号的数据源）。"""
    lock = RedisSessionLock(r)
    token = new_owner_token()
    await lock.acquire(_SID, token, ttl_s=0.05)
    await asyncio.sleep(0.1)
    assert await lock.extend(_SID, token, ttl_s=30.0) is False


async def test_reacquire_after_release(r) -> None:
    """释放后原 owner 与新 owner 均可重新获取（锁无粘性）。"""
    lock = RedisSessionLock(r)
    t1 = new_owner_token()
    await lock.acquire(_SID, t1)
    await lock.release(_SID, t1)
    assert await lock.acquire(_SID, t1) is True
    await lock.release(_SID, t1)
    assert await lock.acquire(_SID, new_owner_token()) is True


async def test_hold_session_lock_raises_when_held(r) -> None:
    """先手持锁，hold_session_lock 二进 → SessionLockHeld（M3.2 的 409 信号源）。"""
    lock = RedisSessionLock(r)
    await lock.acquire(_SID, new_owner_token())
    with pytest.raises(SessionLockHeld, match=_SID):
        async with hold_session_lock(lock, _SID):
            pass


async def test_watchdog_renews_via_injected_sleep(r) -> None:
    """看门狗按 renew_interval 节律调 extend（注入 sleep 缝计数，零真实计时断言）。"""
    lock = RedisSessionLock(r)
    calls, sleeper = _stepping_sleep(3)
    async with hold_session_lock(lock, _SID, ttl_s=30.0, renew_interval_s=10.0, sleep=sleeper) as held:
        for _ in range(200):
            if len(calls) > 3:
                break
            await asyncio.sleep(0.01)
        assert calls[:3] == [10.0, 10.0, 10.0]
        assert not held.lost.is_set()
        assert await r.get(_KEY) == held.owner_token
    assert await r.get(_KEY) is None


async def test_watchdog_sets_lost_on_extend_failure() -> None:
    """续期失败 → lost 置位且看门狗停止——不重试、不切后端（D13）。"""
    stub = _StubLock(extend_result=False)
    calls, sleeper = _stepping_sleep(5)
    async with hold_session_lock(stub, "lk-wd", renew_interval_s=1.0, sleep=sleeper) as held:
        for _ in range(200):
            if held.lost.is_set():
                break
            await asyncio.sleep(0.01)
        assert held.lost.is_set()
        n = stub.extend_calls
        assert n == 1
        for _ in range(10):
            await asyncio.sleep(0.01)
        assert stub.extend_calls == n


async def test_hold_releases_on_exit(r) -> None:
    """with 正常退出释放锁；异常退出同样释放（finally 语义）。"""
    lock = RedisSessionLock(r)
    async with hold_session_lock(lock, _SID) as held:
        assert await r.get(_KEY) == held.owner_token
    assert await r.get(_KEY) is None
    with pytest.raises(RuntimeError, match="测试炸"):
        async with hold_session_lock(lock, _SID):
            raise RuntimeError("测试炸")
    assert await r.get(_KEY) is None

"""M3.10 交付③：EventNotifier——LISTEN 分发/降级轮询/触发器在位（C22 实装面）。

集成测走真 PG 原生连接（pg_notify 直发验证分发机制——事务提交才发是特性，
§4.10 陷阱 4）；触发器在位测在迁移后（CI alembic 先于 pytest）；
无 PG 时沿全仓惯例 skip（db_conn 夹具间接把关）。
"""

from __future__ import annotations

import asyncio
import os

import asyncpg
import pytest
from sqlalchemy import text

from aegis.api.notify import EventNotifier

TEST_DATABASE_URL = os.environ.get("AEGIS_TEST_DATABASE_URL", "postgresql+asyncpg://aegis:aegis@localhost:5432/aegis")
_RAW_DSN = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def _pg_available() -> bool:
    try:
        conn = await asyncpg.connect(_RAW_DSN, timeout=2)
    except Exception:
        if os.environ.get("CI"):
            raise
        return False
    await conn.close()
    return True


async def test_wait_for_wakes_on_notify() -> None:
    """LISTEN 分发：pg_notify 到达 → 对应 session 的等待者在超时前被唤醒。"""
    if not await _pg_available():
        pytest.skip("本地 PostgreSQL 未启动")
    notifier = EventNotifier(TEST_DATABASE_URL, poll_interval_s=0.2)
    await notifier.start()
    try:
        await asyncio.sleep(0.3)  # 等 LISTEN 连接就绪（后台任务建连）
        sender = await asyncpg.connect(_RAW_DSN)
        try:

            async def _fire() -> None:
                await asyncio.sleep(0.1)
                await sender.execute("SELECT pg_notify('aegis_events', 'sess-notify-1:7')")

            task = asyncio.create_task(_fire())
            started = asyncio.get_running_loop().time()
            await notifier.wait_for("sess-notify-1", timeout_s=5.0)
            elapsed = asyncio.get_running_loop().time() - started
            await task
            assert elapsed < 4.0  # 被通知唤醒而非熬满超时（阈值放宽防慢机误报，不进 CI 纪律的时序断言豁免线内）
        finally:
            await sender.close()
    finally:
        await notifier.stop()


async def test_wait_for_degrades_to_poll_when_not_started() -> None:
    """C22 兜底：无 LISTEN 连接（未启动/断连）→ wait_for 按轮询节拍返回，绝不悬死。"""
    notifier = EventNotifier("postgresql+asyncpg://unused/unused", poll_interval_s=0.05)
    started = asyncio.get_running_loop().time()
    await notifier.wait_for("any-session", timeout_s=30.0)
    elapsed = asyncio.get_running_loop().time() - started
    assert elapsed < 5.0  # 轮询节拍量级而非 30s 超时量级


class _FakeConn:
    """确定性假连接（M4.7-A：(67)(68) 测试面）：黑洞形态无法用真 PG 本地复现——
    probe_error 注入让"心跳发现死连接"变成可断言行为，而非等 25s 的运气。"""

    def __init__(self, probe_error: Exception | None = None) -> None:
        self.probe_error = probe_error
        self.probes = 0
        self.closed = False

    async def add_listener(self, channel: str, callback: object) -> None:
        return None

    def is_closed(self) -> bool:
        return self.closed

    async def execute(self, sql: str) -> str:
        self.probes += 1
        if self.probe_error is not None:
            raise self.probe_error
        return "SELECT 1"

    async def close(self) -> None:
        self.closed = True


async def test_heartbeat_probes_healthy_connection(monkeypatch) -> None:
    """(68) 正面：健康连接被周期性 SELECT 1 探测，_conn 保持在场（不误降级）。"""
    fake = _FakeConn()
    monkeypatch.setattr("aegis.api.notify.asyncpg.connect", lambda dsn: _as_coro(fake))
    notifier = EventNotifier("postgresql+asyncpg://unused/unused", heartbeat_interval_s=0.02)
    await notifier.start()
    try:
        await asyncio.sleep(0.2)
        assert fake.probes >= 2, "心跳探针没有周期性运行"
        assert notifier._conn is fake, "健康探测不该触发降级"
    finally:
        await notifier.stop()


async def test_heartbeat_failure_degrades_and_wakes_in_flight_waiter(monkeypatch) -> None:
    """(68)+(67)：探针失败（黑洞形态的注入替身）→ 降级 _conn=None，且**在途**等待者
    被立刻唤醒——不唤醒则该等待者抱着死 Event 熬满 30s（降级只对新来的人生效）。"""
    fake = _FakeConn(probe_error=ConnectionError("black hole"))
    monkeypatch.setattr("aegis.api.notify.asyncpg.connect", lambda dsn: _as_coro(fake))
    notifier = EventNotifier("postgresql+asyncpg://unused/unused", poll_interval_s=60.0, heartbeat_interval_s=0.1)
    await notifier.start()
    try:
        await asyncio.sleep(0.03)  # 建连完成、首次探针（0.1s）之前——等待者须在降级前入桶
        assert notifier._conn is fake
        started = asyncio.get_running_loop().time()
        await notifier.wait_for("sess-inflight", timeout_s=30.0)
        elapsed = asyncio.get_running_loop().time() - started
        assert elapsed < 5.0, "在途等待者未被断连唤醒（熬向 30s 超时）"
        assert notifier._conn is None, "探针失败后应处于降级态"
    finally:
        await notifier.stop()


async def test_stop_wakes_in_flight_waiters(monkeypatch) -> None:
    """(67) 停机路径：stop() 取消后台任务 → finally 同样唤醒在途等待者（优雅停机
    不该被一个挂着的 SSE 等待卡住超时周期）。"""
    fake = _FakeConn()
    monkeypatch.setattr("aegis.api.notify.asyncpg.connect", lambda dsn: _as_coro(fake))
    notifier = EventNotifier("postgresql+asyncpg://unused/unused", heartbeat_interval_s=60.0)
    await notifier.start()
    await asyncio.sleep(0.03)
    assert notifier._conn is fake
    waiter = asyncio.create_task(notifier.wait_for("sess-stop", timeout_s=30.0))
    await asyncio.sleep(0.03)  # 等待者入桶
    started = asyncio.get_running_loop().time()
    await notifier.stop()
    await waiter
    assert asyncio.get_running_loop().time() - started < 5.0, "stop 未唤醒在途等待者"


def _as_coro(value):
    async def _inner():
        return value

    return _inner()


async def test_events_insert_trigger_in_place(db_session_factory) -> None:
    """D10 触发器在位（迁移面）：trg_events_notify 挂在 events 表上（真实发通知由
    真实链路验收作证——事务提交才发，SAVEPOINT 夹具下不可直测）。"""
    async with db_session_factory() as s:
        row = (
            await s.execute(
                text("SELECT tgname FROM pg_trigger WHERE tgname = 'trg_events_notify' AND NOT tgisinternal")
            )
        ).scalar_one_or_none()
    assert row == "trg_events_notify"

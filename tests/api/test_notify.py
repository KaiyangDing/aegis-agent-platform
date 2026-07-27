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

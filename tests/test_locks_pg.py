"""M2.9 交付②：PG advisory 降级三件套 + 停 Redis（dead_r）互斥保住。

夹具注意（m2.9 §5.2）：advisory 锁是连接作用域——互斥断言必须来自两条不同
物理连接。conftest 的 db_conn/db_session_factory 是单连接+外层事务，对同一
PG 会话锁可重入会假绿（§7 坑 4），本文件自建双 NullPool 引擎。
advisory 锁不触表：无数据污染、无需回滚，引擎 dispose 即释放一切。
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from aegis.core.locks import FailoverSessionLock, PgAdvisorySessionLock, RedisSessionLock, new_owner_token

TEST_DATABASE_URL = os.environ.get("AEGIS_TEST_DATABASE_URL", "postgresql+asyncpg://aegis:aegis@localhost:5432/aegis")


@pytest.fixture
async def pg_engines():
    """两个独立 NullPool 引擎：两条真实物理连接的替身（跨副本互斥的正身验证）。"""
    e1 = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    e2 = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with e1.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        await e1.dispose()
        await e2.dispose()
        if os.environ.get("CI"):
            raise  # CI 里 PG 必须在——静默跳过等于守卫失效
        pytest.skip("本地 PostgreSQL 未启动：docker compose -f deploy/docker-compose.yml up -d")
    yield e1, e2
    await e1.dispose()
    await e2.dispose()


async def test_pg_acquire_and_release(pg_engines) -> None:
    """获取 → 释放 → 另一实例可获取（专用连接生命周期正确闭合）。"""
    e1, e2 = pg_engines
    a, b = PgAdvisorySessionLock(e1), PgAdvisorySessionLock(e2)
    t = new_owner_token()
    assert await a.acquire("pg-1", t) is True
    assert await a.release("pg-1", t) is True
    t2 = new_owner_token()
    assert await b.acquire("pg-1", t2) is True
    await b.release("pg-1", t2)


async def test_pg_mutual_exclusion_across_connections(pg_engines) -> None:
    """session 级锁跨物理连接互斥的正身验证：A 持锁期间 B 获取恒 False。"""
    e1, e2 = pg_engines
    a, b = PgAdvisorySessionLock(e1), PgAdvisorySessionLock(e2)
    t = new_owner_token()
    assert await a.acquire("pg-2", t) is True
    assert await b.acquire("pg-2", new_owner_token()) is False
    await a.release("pg-2", t)


async def test_pg_release_wrong_owner_refused(pg_engines) -> None:
    """错 token 释放被拒且锁仍互斥——owner 语义在应用层兜（advisory 锁认连接不认 token）。"""
    e1, e2 = pg_engines
    a, b = PgAdvisorySessionLock(e1), PgAdvisorySessionLock(e2)
    t = new_owner_token()
    await a.acquire("pg-3", t)
    assert await a.release("pg-3", new_owner_token()) is False
    assert await b.acquire("pg-3", new_owner_token()) is False
    await a.release("pg-3", t)


async def test_pg_lock_survives_other_statements(pg_engines) -> None:
    """C4 灵魂断言（session 级 ≠ xact 级）：持锁后跑完整 commit 事务、锁依旧——
    误用 xact 级锁会在事务/语句结束时蒸发，B 就能获取。"""
    e1, e2 = pg_engines
    a, b = PgAdvisorySessionLock(e1), PgAdvisorySessionLock(e2)
    t = new_owner_token()
    await a.acquire("pg-4", t)
    async with e1.begin() as conn:  # 同引擎另一条连接跑一个提交事务（模拟事件写入）
        await conn.execute(text("SELECT 1"))
    assert await b.acquire("pg-4", new_owner_token()) is False
    await a.release("pg-4", t)


async def test_pg_hashtext_is_server_side(pg_engines) -> None:
    """两实例（两副本替身）对同 session_id 锁同一把（服务端 hashtext 稳定）；异键互不干扰。"""
    e1, e2 = pg_engines
    a, b = PgAdvisorySessionLock(e1), PgAdvisorySessionLock(e2)
    t = new_owner_token()
    await a.acquire("pg-5", t)
    assert await b.acquire("pg-5", new_owner_token()) is False
    t2 = new_owner_token()
    assert await b.acquire("pg-5-other", t2) is True
    await a.release("pg-5", t)
    await b.release("pg-5-other", t2)


async def test_stop_redis_failover_keeps_mutex(pg_engines, dead_r) -> None:
    """停 Redis 验证（00 §6.2 毕业行）：降级到 PG 授予，第二实例同会话获取 False——互斥不丢。"""
    e1, e2 = pg_engines
    f1 = FailoverSessionLock(RedisSessionLock(dead_r), PgAdvisorySessionLock(e1))
    f2 = FailoverSessionLock(RedisSessionLock(dead_r), PgAdvisorySessionLock(e2))
    t = new_owner_token()
    assert await f1.acquire("pg-6", t) is True
    assert await f2.acquire("pg-6", new_owner_token()) is False
    await f1.release("pg-6", t)


async def test_stop_redis_release_routes_to_pg(pg_engines, dead_r) -> None:
    """降级授予的锁 release 路由到 PG 后端；释放后第二实例可获取。"""
    e1, e2 = pg_engines
    f1 = FailoverSessionLock(RedisSessionLock(dead_r), PgAdvisorySessionLock(e1))
    t = new_owner_token()
    await f1.acquire("pg-7", t)
    assert await f1.release("pg-7", t) is True
    f2 = FailoverSessionLock(RedisSessionLock(dead_r), PgAdvisorySessionLock(e2))
    t2 = new_owner_token()
    assert await f2.acquire("pg-7", t2) is True
    # 显式释放收尾：acquire 后不释放会让专用连接挂在 _held 里，NullPool dispose 不管
    # 已 checkout 的连接，最终靠 GC 在已关闭的 loop 上 terminate——正是坑 3 的现场版
    await f2.release("pg-7", t2)

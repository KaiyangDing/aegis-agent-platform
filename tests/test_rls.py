"""M3.3①：RLS + 低权角色 + SET LOCAL 事务钩子——真提交语义（不能用 SAVEPOINT 夹具）。

前提：`uv run alembic upgrade head` 已建 aegis_app 角色与五表策略——conftest 的
create_all 不建角色/策略，本地首跑必先迁移（CI 步序 alembic→pytest 天然满足）。
夹具自理种子与清理，断言全部过滤到本文件前缀 s-rls-（全库扫描断言纪律，M2.10 教训）。
"""

from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine

from aegis.core.tenant_ctx import install_tenant_guard, tenant_context

OWNER_URL = os.environ.get("AEGIS_TEST_DATABASE_URL", "postgresql+asyncpg://aegis:aegis@localhost:5432/aegis")
APP_URL = os.environ.get("AEGIS_TEST_DATABASE_URL_APP", "postgresql+asyncpg://aegis_app:aegis_app@localhost:5432/aegis")

_SEEDS = [("s-rls-a", "rls-t-a", "u-rls-a"), ("s-rls-b", "rls-t-b", "u-rls-b")]


@pytest.fixture
async def owner_engine():
    engine = create_async_engine(OWNER_URL)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        await engine.dispose()
        if os.environ.get("CI"):
            raise
        pytest.skip("本地 PostgreSQL 未启动：docker compose -f deploy/docker-compose.yml up -d")
    yield engine
    await engine.dispose()


@pytest.fixture
async def rls_ready(owner_engine):
    """前置核查（角色+策略在位）+ 种子两租户各一行 + 过滤式清理。"""
    async with owner_engine.connect() as conn:
        role = (await conn.execute(text("SELECT count(*) FROM pg_roles WHERE rolname = 'aegis_app'"))).scalar_one()
        policy = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM pg_policies WHERE tablename = 'sessions' AND policyname = 'tenant_isolation'"
                )
            )
        ).scalar_one()
    if not (role and policy):
        if os.environ.get("CI"):
            raise RuntimeError("CI 里角色/策略必须在位——检查 alembic upgrade 步")
        pytest.skip("aegis_app 角色或 RLS 策略未建：先 uv run alembic upgrade head")
    async with owner_engine.begin() as conn:
        await conn.execute(text("DELETE FROM sessions WHERE id LIKE 's-rls-%'"))
        for sid, tid, uid in _SEEDS:
            # 裸 SQL 必须显式给全列：lease_generation/recovery_count 的 default=0 在 ORM 层，
            # 对裸 INSERT 不生效（M3.1 陷阱清单原条，本文件首版实踩——NOT NULL 违反）
            await conn.execute(
                text(
                    "INSERT INTO sessions (id, tenant_id, user_id, run_state, lease_generation, recovery_count) "
                    "VALUES (:s, :t, :u, 'idle', 0, 0)"
                ),
                {"s": sid, "t": tid, "u": uid},
            )
    yield
    async with owner_engine.begin() as conn:
        await conn.execute(text("DELETE FROM sessions WHERE id LIKE 's-rls-%'"))


@pytest.fixture
async def rls_engine(rls_ready):
    """低权引擎（aegis_app）+ 租户钩子——被测主体。每测试新建（跨 event loop 纪律）。"""
    engine = create_async_engine(APP_URL)
    install_tenant_guard(engine)
    yield engine
    await engine.dispose()


_PICK = text("SELECT id FROM sessions WHERE id LIKE 's-rls-%' ORDER BY id")


async def _visible_ids(engine) -> list[str]:
    async with engine.connect() as conn:
        async with conn.begin():
            return list((await conn.execute(_PICK)).scalars().all())


async def test_no_context_bare_sql_returns_empty(rls_engine) -> None:
    """02 §7.2 点名测试①：绕过 Repository 的裸 SQL、未设上下文 → 空集（fail-closed）。"""
    assert await _visible_ids(rls_engine) == []


async def test_context_sees_only_own_tenant(rls_engine) -> None:
    with tenant_context("rls-t-a"):
        assert await _visible_ids(rls_engine) == ["s-rls-a"]
    with tenant_context("rls-t-b"):
        assert await _visible_ids(rls_engine) == ["s-rls-b"]


async def test_concurrent_two_tenants_do_not_leak(rls_engine) -> None:
    """02 §7.2 点名测试②：并发双租户多轮查询互不见对方（连接池复用下上下文不串）。"""

    async def probe(tid: str, expect: str) -> None:
        with tenant_context(tid):
            for _ in range(10):
                assert await _visible_ids(rls_engine) == [expect]

    await asyncio.gather(probe("rls-t-a", "s-rls-a"), probe("rls-t-b", "s-rls-b"))


async def test_insert_wrong_tenant_rejected(rls_engine) -> None:
    """WITH CHECK 生效：以 a 的上下文写 b 的行 → RLS 拒绝（42501 → ProgrammingError）。"""
    with tenant_context("rls-t-a"):
        with pytest.raises(ProgrammingError):
            async with rls_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO sessions (id, tenant_id, user_id, run_state, lease_generation, recovery_count) "
                        "VALUES ('s-rls-x', 'rls-t-b', 'u', 'idle', 0, 0)"
                    )
                )


async def test_insert_own_tenant_allowed(rls_engine) -> None:
    with tenant_context("rls-t-a"):
        async with rls_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO sessions (id, tenant_id, user_id, run_state, lease_generation, recovery_count) "
                    "VALUES ('s-rls-new', 'rls-t-a', 'u', 'idle', 0, 0)"
                )
            )
        assert await _visible_ids(rls_engine) == ["s-rls-a", "s-rls-new"]


async def test_owner_engine_bypasses_for_maintenance(owner_engine, rls_ready) -> None:
    """D4 语义留证：维护面 owner（compose 里即超管）跨租户全见——reaper/种子/对账的合法形态。"""
    async with owner_engine.connect() as conn:
        rows = list((await conn.execute(_PICK)).scalars().all())
    assert rows == ["s-rls-a", "s-rls-b"]

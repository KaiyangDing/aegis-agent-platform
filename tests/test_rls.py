"""M3.3①：RLS + 低权角色 + SET LOCAL 事务钩子——真提交语义（不能用 SAVEPOINT 夹具）。

前提：`uv run alembic upgrade head` 已建 aegis_app 角色与五表策略——conftest 的
create_all 不建角色/策略，本地首跑必先迁移（CI 步序 alembic→pytest 天然满足）。
夹具自理种子与清理，断言全部过滤到本文件前缀 s-rls-（全库扫描断言纪律，M2.10 教训）。
"""

from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal

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


# ---------------------------------------------------------------------------
# M3.4 增量：documents/chunks——"新表迁移自带 RLS"前置义务的对账（plans/m3-detailed 14c 登记）
# ---------------------------------------------------------------------------

_RAG_DOC_PICK = text("SELECT id FROM documents WHERE id LIKE 'd-rls-%' ORDER BY id")
_RAG_CHUNK_PICK = text("SELECT document_id FROM chunks WHERE document_id LIKE 'd-rls-%' ORDER BY document_id")


@pytest.fixture
async def rag_tables_ready(owner_engine):
    """documents/chunks 已建才继续（迁移未跑：本地 skip / CI 硬失败——与 rls_ready 同款门）。"""
    async with owner_engine.connect() as conn:
        ok = (
            await conn.execute(
                text("SELECT to_regclass('documents') IS NOT NULL AND to_regclass('chunks') IS NOT NULL")
            )
        ).scalar_one()
    if not ok:
        if os.environ.get("CI"):
            raise RuntimeError("CI 里 documents/chunks 必须在位——检查 M3.4 迁移是否入链")
        pytest.skip("documents/chunks 未建：先 uv run alembic upgrade head")
    yield owner_engine


async def test_vector_extension_enabled(rag_tables_ready) -> None:
    """迁移首句的存在性凭证：库内 extension 已启用（M3.0 核对 0-17 时 extversion 还是空）。"""
    async with rag_tables_ready.connect() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'"))).scalar_one()
    assert n == 1


async def test_rag_tables_rls_policies_in_place(rag_tables_ready) -> None:
    """前置义务本体：DEFAULT PRIVILEGES 只授 DML、RLS 不隐式继承——两表策略必须随迁移自带。"""
    async with rag_tables_ready.connect() as conn:
        n = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM pg_policies "
                    "WHERE tablename IN ('documents', 'chunks') AND policyname = 'tenant_isolation'"
                )
            )
        ).scalar_one()
    assert n == 2


async def test_hnsw_cosine_index_exists(rag_tables_ready) -> None:
    """HNSW 手写索引在位且是余弦簇——autogenerate 不会生成它，忘写=检索退化全表扫（§4.4 陷阱 2）。"""
    async with rag_tables_ready.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE tablename = 'chunks' AND indexname = 'ix_chunks_embedding_hnsw'"
                )
            )
        ).one_or_none()
    assert row is not None
    assert "USING hnsw" in row[0] and "vector_cosine_ops" in row[0]


@pytest.fixture
async def rag_rls_seeded(rag_tables_ready):
    """两租户各一文档一块（owner 种子、过滤式清理——前缀 d-rls-，全库扫描断言纪律）。"""
    owner = rag_tables_ready
    async with owner.begin() as conn:
        await conn.execute(text("DELETE FROM chunks WHERE document_id LIKE 'd-rls-%'"))
        await conn.execute(text("DELETE FROM documents WHERE id LIKE 'd-rls-%'"))
        for doc, tid in (("d-rls-a", "rls-t-a"), ("d-rls-b", "rls-t-b")):
            # 裸 INSERT 显式给全列：chunk_count/meta 的 ORM 默认对裸 SQL 不生效（M3.3 偏差 ⒀ 同课）
            await conn.execute(
                text(
                    "INSERT INTO documents (id, tenant_id, source, status, chunk_count, meta) "
                    "VALUES (:d, :t, 'seed.md', 'pending', 0, '{}'::jsonb)"
                ),
                {"d": doc, "t": tid},
            )
            await conn.execute(
                text(
                    "INSERT INTO chunks (document_id, tenant_id, seq, text, meta) "
                    "VALUES (:d, :t, 0, '种子块', '{}'::jsonb)"
                ),
                {"d": doc, "t": tid},
            )
    yield owner
    async with owner.begin() as conn:
        await conn.execute(text("DELETE FROM chunks WHERE document_id LIKE 'd-rls-%'"))
        await conn.execute(text("DELETE FROM documents WHERE id LIKE 'd-rls-%'"))


@pytest.fixture
async def rag_rls_engine(rag_rls_seeded):
    """低权引擎（与 rls_engine 同形态；依赖 rag 种子而非 sessions 种子）。每测试新建，跨 event loop 纪律。"""
    engine = create_async_engine(APP_URL)
    install_tenant_guard(engine)
    yield engine
    await engine.dispose()


async def test_rag_tables_isolated_by_tenant(rag_rls_engine) -> None:
    """对抗场景①的 chunks 面：未设上下文空集（fail-closed）；a 只见 a、b 只见 b。"""

    async def picks(stmt) -> list[str]:
        async with rag_rls_engine.connect() as conn:
            async with conn.begin():
                return list((await conn.execute(stmt)).scalars().all())

    assert await picks(_RAG_DOC_PICK) == []
    with tenant_context("rls-t-a"):
        assert await picks(_RAG_DOC_PICK) == ["d-rls-a"]
        assert await picks(_RAG_CHUNK_PICK) == ["d-rls-a"]
    with tenant_context("rls-t-b"):
        assert await picks(_RAG_CHUNK_PICK) == ["d-rls-b"]


async def test_rag_insert_wrong_tenant_rejected(rag_rls_engine) -> None:
    """WITH CHECK 在写路径生效：以 a 的上下文伪造 b 的块 → 42501（ProgrammingError）。"""
    with tenant_context("rls-t-a"):
        with pytest.raises(ProgrammingError):
            async with rag_rls_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO chunks (document_id, tenant_id, seq, text, meta) "
                        "VALUES ('d-rls-x', 'rls-t-b', 0, 'x', '{}'::jsonb)"
                    )
                )


async def test_rag_insert_own_tenant_allowed(rag_rls_engine) -> None:
    """放行面与拒绝面成对（sessions 先例同构）：本租户写入过 WITH CHECK，且 id 不给、走 nextval——
    正面验证 DEFAULT PRIVILEGES 的序列 USAGE 授权（拒绝面区分不了 42501 的两种来源，只有放行面能证明授权链活着）。"""
    with tenant_context("rls-t-a"):
        async with rag_rls_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO chunks (document_id, tenant_id, seq, text, meta) "
                    "VALUES ('d-rls-a', 'rls-t-a', 1, '新块', '{}'::jsonb)"
                )
            )
        async with rag_rls_engine.connect() as conn:
            async with conn.begin():
                n = (await conn.execute(text("SELECT count(*) FROM chunks WHERE document_id = 'd-rls-a'"))).scalar_one()
    assert n == 2


# ---------------------------------------------------------------------------
# M3.7 增量：mock_orders/mock_write_ops——前置义务对账（plans/m3-detailed 14g 登记）
# ---------------------------------------------------------------------------

_MOCK_ORDER_PICK = text("SELECT id FROM mock_orders WHERE id LIKE 'mo-rls-%' ORDER BY id")


@pytest.fixture
async def mock_tables_ready(owner_engine):
    """mock 两表已建才继续（迁移未跑：本地 skip / CI 硬失败——rag_tables_ready 同款门）。"""
    async with owner_engine.connect() as conn:
        ok = (
            await conn.execute(
                text("SELECT to_regclass('mock_orders') IS NOT NULL AND to_regclass('mock_write_ops') IS NOT NULL")
            )
        ).scalar_one()
    if not ok:
        if os.environ.get("CI"):
            raise RuntimeError("CI 里 mock_orders/mock_write_ops 必须在位——检查 M3.7 迁移是否入链")
        pytest.skip("mock_orders/mock_write_ops 未建：先 uv run alembic upgrade head")
    yield owner_engine


async def test_mock_tables_rls_policies_in_place(mock_tables_ready) -> None:
    """前置义务本体（M3.4 同款）：DEFAULT PRIVILEGES 只授 DML、RLS 不隐式继承——两表策略随迁移自带。"""
    async with mock_tables_ready.connect() as conn:
        n = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM pg_policies "
                    "WHERE tablename IN ('mock_orders', 'mock_write_ops') AND policyname = 'tenant_isolation'"
                )
            )
        ).scalar_one()
    assert n == 2


@pytest.fixture
async def mock_rls_seeded(mock_tables_ready):
    """两租户各一单（owner 种子、过滤式清理——前缀 mo-rls-/wo-rls-，全库扫描断言纪律）。"""
    owner = mock_tables_ready
    async with owner.begin() as conn:
        await conn.execute(text("DELETE FROM mock_write_ops WHERE idempotency_key LIKE 'wo-rls-%'"))
        await conn.execute(text("DELETE FROM mock_orders WHERE id LIKE 'mo-rls-%'"))
        for oid, tid in (("mo-rls-a", "rls-t-a"), ("mo-rls-b", "rls-t-b")):
            # 裸 INSERT 显式给全列：items 无默认、必须给（M3.3 偏差 ⒀ 同课）
            await conn.execute(
                text(
                    "INSERT INTO mock_orders (id, tenant_id, user_id, status, paid_amount, items) "
                    "VALUES (:o, :t, 'u-rls', 'paid', 199.99, '{}'::jsonb)"
                ),
                {"o": oid, "t": tid},
            )
    yield owner
    async with owner.begin() as conn:
        await conn.execute(text("DELETE FROM mock_write_ops WHERE idempotency_key LIKE 'wo-rls-%'"))
        await conn.execute(text("DELETE FROM mock_orders WHERE id LIKE 'mo-rls-%'"))


@pytest.fixture
async def mock_rls_engine(mock_rls_seeded):
    """低权引擎（rls_engine 同形态；依赖 mock 种子）。每测试新建，跨 event loop 纪律。"""
    engine = create_async_engine(APP_URL)
    install_tenant_guard(engine)
    yield engine
    await engine.dispose()


async def test_mock_orders_isolated_by_tenant(mock_rls_engine) -> None:
    """对抗③的库层底座：未设上下文空集（fail-closed）；a 只见 a 单、b 只见 b 单——
    工具体内归属校验（交付③）之下还有这层兜底。"""

    async def picks() -> list[str]:
        async with mock_rls_engine.connect() as conn:
            async with conn.begin():
                return list((await conn.execute(_MOCK_ORDER_PICK)).scalars().all())

    assert await picks() == []
    with tenant_context("rls-t-a"):
        assert await picks() == ["mo-rls-a"]
    with tenant_context("rls-t-b"):
        assert await picks() == ["mo-rls-b"]


async def test_mock_write_op_wrong_tenant_rejected(mock_rls_engine) -> None:
    """WITH CHECK 写路径：以 a 的上下文写 b 的去重行 → 42501（ProgrammingError）。"""
    with tenant_context("rls-t-a"):
        with pytest.raises(ProgrammingError):
            async with mock_rls_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO mock_write_ops (idempotency_key, kind, tenant_id, payload) "
                        "VALUES ('wo-rls-x', 'refund', 'rls-t-b', '{}'::jsonb)"
                    )
                )


async def test_mock_write_op_own_tenant_allowed(mock_rls_engine) -> None:
    """放行面与拒绝面成对（rag 先例同构）：本租户写去重行过 WITH CHECK——授权链活着的正面证明。"""
    with tenant_context("rls-t-a"):
        async with mock_rls_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO mock_write_ops (idempotency_key, kind, tenant_id, payload) "
                    "VALUES ('wo-rls-ok', 'refund', 'rls-t-a', '{}'::jsonb)"
                )
            )
        async with mock_rls_engine.connect() as conn:
            async with conn.begin():
                n = (
                    await conn.execute(text("SELECT count(*) FROM mock_write_ops WHERE idempotency_key = 'wo-rls-ok'"))
                ).scalar_one()
    assert n == 1


# ---------------------------------------------------------------------------
# M4.0② 增量节：候选④——stream 端点的 "admin 平台级" 在 RLS 在场时不成立
# ---------------------------------------------------------------------------
# 缺陷本体（M4.0① 探针实测）：`_ensure_owned` 走常规 app 工厂读 RLS 名单内的
# `sessions`，而 auth 对**所有角色**无差别 `current_tenant_id.set()`（auth.py:144，
# admin 无豁免）→ admin 拉他租会话恒 404「会话不存在」。代码"只对 USER 校验归属"
# 的写法说明**意图是放行**，是 RLS 悄悄拦下（#46 家族第二例：加一层防线会让上层
# 判断变成死代码）。性质 fail-closed 不泄漏，但能力声明与 02 §7.1 矩阵不符，且
# **同一提交 `d1d2275` 的兄弟端点 `events_view.py:38-40` 就显式走了 owner 查读缝**
# ——两个端点对同一问题给了两个答案（admin 会收到"events 看得见、stream 说不存在"）。
# 既有测试全绿因 #47：测试连 owner，RLS 不在场。
#
# 修法：两处 `SessionRecord` 读（归属校验 + 关流判据）改走 owner 查读缝
# （`app.state.approvals_lookup`，M3.9② 拍板Ⅲ 已备好的平台视角）。事件读**不用改**
# ——`events` 无 tenant_id 列、不在 RLS 名单内（P5：仅带 tenant_id 列的表）。


# 测法说明：修复点是**调用点传哪个 factory**（而非 `_ensure_owned` 本身），故必须走
# 端点级——app 侧 session_factory 连 RLS 低权引擎、approvals_lookup 连 owner 引擎，
# 这正是生产装配形态（main.py:99 `approvals_lookup or get_owner_session_factory()`）。
# 顺带这是 #47「测试跑在无 RLS 世界」的一块补丁：本条真的把业务端点放进了 RLS 在场的世界。


class _NullGateway:
    def complete(self, req):  # pragma: no cover —— GET 通道不触 LLM
        raise AssertionError("GET 通道绝不调用 LLM")


class _Limiter:
    async def try_take(self, scope, rate, capacity, cost=1.0):
        return (True, 0.0)


async def test_admin_cross_tenant_stream_is_platform_level(rls_engine, owner_engine) -> None:
    """admin 拉他租会话的流：02 §7.1 矩阵声明的"平台级"必须真的成立（≠404）。

    修复前红：`_ensure_owned` 走 app 工厂 → RLS 过滤 → `scalar_one_or_none()` 得 None
    → 404「会话不存在」。修复后绿：归属校验与关流判据两处 SessionRecord 读改走
    owner 查读缝；事件读**不改**（events 无 tenant_id、不在 RLS 名单内）。
    """
    import httpx
    from pydantic import SecretStr
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from aegis.api.auth import issue_token
    from aegis.api.main import create_app
    from aegis.api.notify import EventNotifier
    from aegis.core.config import Settings
    from aegis.core.tenancy import Role
    from aegis.runtime.runtime import AgentRuntime

    secret = "m4-rls-probe-secret-key-32bytes-min!!"
    app_factory = async_sessionmaker(rls_engine, expire_on_commit=False)
    owner_factory = async_sessionmaker(owner_engine, expire_on_commit=False)
    gw = _NullGateway()
    app = create_app(
        Settings(jwt_secret=SecretStr(secret)),
        session_factory=app_factory,
        runtime=AgentRuntime(gw, app_factory),
        limiter=_Limiter(),
        gateway=gw,
        approvals_lookup=owner_factory,  # 生产同形：平台视角查读缝
        notifier=EventNotifier("postgresql+asyncpg://unused/unused", poll_interval_s=0.05),
        msg_redis=None,
    )
    token = issue_token(user_id="admin-rls", tenant_id="rls-t-a", role=Role.ADMIN, ttl_s=3600, secret=secret)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        # s-rls-b 属租户 rls-t-b（rls_ready 种子）、idle 且无事件 → 回放空、立即关流
        resp = await c.get("/v1/sessions/s-rls-b/stream", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"admin 平台级不成立：{resp.status_code} {resp.text}"


async def test_user_cross_tenant_stream_still_404(rls_engine, owner_engine) -> None:
    """反向对照（防修过头）：普通用户拉他租会话仍须 404，且理由是**归属判定**而非 RLS。

    改用 owner 查读缝后，`row` 不再被 RLS 抹掉——挡住越权的必须是 `_ensure_owned`
    里那条 USER 分支（#19 不泄露存在性）。若修复顺手把该分支也绕过，本条立刻变红。
    """
    import httpx
    from pydantic import SecretStr
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from aegis.api.auth import issue_token
    from aegis.api.main import create_app
    from aegis.api.notify import EventNotifier
    from aegis.core.config import Settings
    from aegis.core.tenancy import Role
    from aegis.runtime.runtime import AgentRuntime

    secret = "m4-rls-probe-secret-key-32bytes-min!!"
    app_factory = async_sessionmaker(rls_engine, expire_on_commit=False)
    owner_factory = async_sessionmaker(owner_engine, expire_on_commit=False)
    gw = _NullGateway()
    app = create_app(
        Settings(jwt_secret=SecretStr(secret)),
        session_factory=app_factory,
        runtime=AgentRuntime(gw, app_factory),
        limiter=_Limiter(),
        gateway=gw,
        approvals_lookup=owner_factory,
        notifier=EventNotifier("postgresql+asyncpg://unused/unused", poll_interval_s=0.05),
        msg_redis=None,
    )
    token = issue_token(user_id="u-rls-a", tenant_id="rls-t-a", role=Role.USER, ttl_s=3600, secret=secret)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/v1/sessions/s-rls-b/stream", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


async def test_cross_tenant_session_id_collision_returns_404_not_500(rls_engine, owner_engine) -> None:
    """M4.0③（#46）：他租已占用的 session_id 必须 404，不得 500。

    缺陷链（M3 复盘站 3 探针实测）：`_ensure_session` 的 SELECT 被 RLS 过滤成 None
    → 误判"首见"走建行 → INSERT 撞 PK → `IntegrityError` → 回读**仍被 RLS 过滤成空**
    → `.scalar_one()` 抛 `NoResultFound` → 500。根因是时序：`_ensure_session` 写于 M3.2、
    RLS 上于 M3.3，`row.tenant_id != principal.tenant_id` 那条归属判定被 RLS 抢答成死代码。
    危害非数据泄漏，但 500 vs 200 构成**存在性 oracle**，与 chat.py:58 docstring
    "不泄露存在性" 的声明不符。修=回读改 `scalar_one_or_none()` + None 抛 404（两行）。

    这也是 #47「测试跑在无 RLS 世界」的又一块补丁：既有 admission 测试连 owner，
    走的是 `row.tenant_id != ...` 那条**在生产中根本到不了**的分支。
    """
    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from aegis.api.auth import Principal
    from aegis.api.chat import _ensure_session
    from aegis.core.tenancy import Role

    app_factory = async_sessionmaker(rls_engine, expire_on_commit=False)
    intruder = Principal(user_id="u-rls-a", tenant_id="rls-t-a", role=Role.USER)
    with tenant_context("rls-t-a"):
        with pytest.raises(HTTPException) as exc:
            await _ensure_session(app_factory, "s-rls-b", intruder)  # 该 id 属 rls-t-b
    assert exc.value.status_code == 404
    assert exc.value.detail == "会话不存在"
    # 未误建行：他租的行仍归他租（owner 视角核证，不受 RLS 影响）
    async with owner_engine.connect() as conn:
        owner_tid = (await conn.execute(text("SELECT tenant_id FROM sessions WHERE id = 's-rls-b'"))).scalar_one()
    assert owner_tid == "rls-t-b"


# ---------------------------------------------------------------------------
# M4.1② 增量节：trace 端点在 RLS 在场世界的 admin 跨租视图——(58) 防线的 CI 证人
# ---------------------------------------------------------------------------
# 风险本体：usage_ledger 在 RLS 名单内，而 auth 对**所有角色**无差别把 ContextVar
# 设为观察者的租户（auth.py:144）。admin 跨租查 trace 时，若账本聚合不显式
# `tenant_context(会话租户)` 覆盖（obs/trace.py 装配器末段），SUM 会被 RLS 过滤成
# 空集且**零报错**——"有账变没账"的静默降级（usage.py:65-67 同款前提；观察池
# (58) 家族）。owner 世界的常规测试对此天然失明（#47），故证人必须住在本文件。
# events 表不受此影响（无 tenant_id 列、不在 RLS 名单——P5），一并在本测内核证。


@pytest.fixture
async def trace_rls_seeded(rls_ready, owner_engine):
    """给 s-rls-b（租户 rls-t-b）种一条事件与一条账本行（owner 面、过滤式清理）。"""
    async with owner_engine.begin() as conn:
        await conn.execute(text("DELETE FROM usage_ledger WHERE request_id LIKE 'rq-rls-%'"))
        await conn.execute(text("DELETE FROM events WHERE session_id LIKE 's-rls-%'"))
        await conn.execute(
            text(
                "INSERT INTO events (id, session_id, run_id, seq, type, schema_version, payload) "
                "VALUES ('ev-rls-1', 's-rls-b', 'run-rls-1', 1, 'assistant_message', 1, CAST(:payload AS jsonb))"
            ),
            {"payload": json.dumps({"content": "已登记手机号 13812345678。"}, ensure_ascii=False)},
        )
        await conn.execute(
            text(
                "INSERT INTO usage_ledger (request_id, tenant_id, session_id, tier, provider, model, "
                "prompt_tokens, completion_tokens, cached, cost) "
                "VALUES ('rq-rls-1', 'rls-t-b', 's-rls-b', 'standard', 'bailian', 'm-rls', 100, 50, false, 0.002)"
            )
        )
    yield
    async with owner_engine.begin() as conn:
        await conn.execute(text("DELETE FROM usage_ledger WHERE request_id LIKE 'rq-rls-%'"))
        await conn.execute(text("DELETE FROM events WHERE session_id LIKE 's-rls-%'"))


async def test_admin_cross_tenant_trace_usage_visible_under_rls(rls_engine, owner_engine, trace_rls_seeded) -> None:
    """admin（租户 a）看租户 b 的 trace：事件在场、payload 已打码、**账本聚合非空**。

    去掉装配器里的 tenant_context 包裹时，本条立刻红在 usage.requests==0——
    观察者上下文（auth 设的 rls-t-a）会让 RLS 把 b 的账本行静默过滤掉。
    """
    import httpx
    from pydantic import SecretStr
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from aegis.api.auth import issue_token
    from aegis.api.main import create_app
    from aegis.api.notify import EventNotifier
    from aegis.core.config import Settings
    from aegis.core.tenancy import Role
    from aegis.runtime.runtime import AgentRuntime

    secret = "m4-rls-probe-secret-key-32bytes-min!!"
    app_factory = async_sessionmaker(rls_engine, expire_on_commit=False)
    owner_factory = async_sessionmaker(owner_engine, expire_on_commit=False)
    gw = _NullGateway()
    app = create_app(
        Settings(jwt_secret=SecretStr(secret)),
        session_factory=app_factory,
        runtime=AgentRuntime(gw, app_factory),
        limiter=_Limiter(),
        gateway=gw,
        approvals_lookup=owner_factory,  # 生产同形：平台视角查读缝
        notifier=EventNotifier("postgresql+asyncpg://unused/unused", poll_interval_s=0.05),
        msg_redis=None,
    )
    token = issue_token(user_id="admin-rls", tenant_id="rls-t-a", role=Role.ADMIN, ttl_s=3600, secret=secret)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/v1/sessions/s-rls-b/events", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"admin 平台级 trace 不成立：{resp.status_code} {resp.text}"
    body = resp.json()
    assert body["tenant_id"] == "rls-t-b"
    content = body["runs"][0]["events"][0]["payload"]["content"]
    assert "***phone_cn***" in content  # 打码在 RLS 世界同样生效（出口单点与世界无关）
    assert "13812345678" not in content
    assert body["usage"]["requests"] == 1  # (58) 防线本体：不包 tenant_context 这里是 0
    assert Decimal(body["usage"]["cost"]) == Decimal("0.002")


# ---------------------------------------------------------------------------
# M4.3 增量节：#47 薄层——"业务入口 × RLS 在场"的三枚交互面证人
# ---------------------------------------------------------------------------
# #47 本体：根 conftest 连 owner（超管+BYPASSRLS+表 owner 三重豁免），业务代码与
# RLS 的交互面在 CI 长期无证人——M3 在此缝踩过四次（M3.5 叶子自包裹 / M3.8 无身份
# 读配置 / M3.12 对账面归零 / #46），前三次全靠人肉真实链路撞出。本节按 #47 建议
# 形态给三类入口各钉一条 rls_engine 行为断言：读租户配置（TenantDirectory）/
# 写账本（MeteringRecorder）/ mock 台账回放读（观察 ㉚）。读会话入口的证人已在
# M4.0②/M4.1② 两节（stream/trace 端点级），不重复。


@pytest.fixture
async def tenants_rls_seeded(rls_ready, owner_engine):
    """tenants 表种 rls-t-a 一行（策略绑行主键即租户 id——迁移 c895f ("tenants","id")；
    created_at/updated_at 走 server_default，裸 INSERT 无需显式给）。"""
    async with owner_engine.begin() as conn:
        await conn.execute(text("DELETE FROM tenants WHERE id LIKE 'rls-t-%'"))
        await conn.execute(
            text(
                "INSERT INTO tenants (id, name, config, token_budget_monthly) "
                "VALUES ('rls-t-a', '证人租户A', CAST(:cfg AS jsonb), 1000)"
            ),
            {"cfg": json.dumps({"approval_threshold": 200}, ensure_ascii=False)},
        )
    yield
    async with owner_engine.begin() as conn:
        await conn.execute(text("DELETE FROM tenants WHERE id LIKE 'rls-t-%'"))


async def test_tenant_directory_config_read_requires_context_under_rls(rls_engine, tenants_rls_seeded) -> None:
    """M3.8 幕 C 实录的 CI 化：无身份读租户配置 = RLS 静默空（None），有身份即读到。

    失败形态是"静默不见"而非报错——TenantDirectory 用 scalar_one_or_none，RLS 空集
    被翻译成"租户不存在"，上层看到的症状与配置漏建一模一样。负例在前正例在后：
    目录只缓存命中（None 不入缓存），该顺序下负例不会经缓存粘给正例。
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from aegis.core.tenancy import TenantDirectory

    directory = TenantDirectory(async_sessionmaker(rls_engine, expire_on_commit=False))
    assert await directory.get_tenant("rls-t-a") is None  # 行在库里，但无上下文时它"不存在"
    with tenant_context("rls-t-a"):
        row = await directory.get_tenant("rls-t-a")
    assert row is not None
    assert row.config["approval_threshold"] == 200


async def test_metering_record_lands_and_rejects_under_rls(rls_engine, rls_ready, owner_engine) -> None:
    """写账本入口的 RLS 双面证人：本租上下文写本租行真落库（WITH CHECK 放行面），
    上下文与行租户不一致 = 42501 响亮拒——写侧从不静默吞行。

    usage 置 cached=True：compute_cost 短路归零不触价目表——证人零价目依赖
    （M4.2① #10 gauge 空价目构造的 record 侧对偶）。落库核数走 owner 面
    （对账读的"非零 sanity"，M3.12 D4 口径）。
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from aegis.gateway.metering import MeteringRecorder
    from aegis.gateway.schema import LLMRequest, Message, UsageChunk

    recorder = MeteringRecorder(async_sessionmaker(rls_engine, expire_on_commit=False), prices={})
    usage = UsageChunk(model="m-rls-m43", prompt_tokens=10, completion_tokens=5, cached=True)
    req_ok = LLMRequest(
        tier="standard",
        messages=[Message(role="user", content="hi")],
        tenant_id="rls-t-a",
        session_id="s-rls-a",
        request_id="rq-rls-m43-ok",
    )
    try:
        with tenant_context("rls-t-a"):
            await recorder.record(req_ok, "bailian", usage)
        async with owner_engine.connect() as conn:
            n = (
                await conn.execute(text("SELECT count(*) FROM usage_ledger WHERE request_id = 'rq-rls-m43-ok'"))
            ).scalar_one()
        assert n == 1  # 真落库，不是"没报错"（非零 sanity）
        req_cross = req_ok.model_copy(update={"tenant_id": "rls-t-b", "request_id": "rq-rls-m43-bad"})
        with tenant_context("rls-t-a"):
            with pytest.raises(ProgrammingError):  # WITH CHECK：42501
                await recorder.record(req_cross, "bailian", usage)
    finally:
        async with owner_engine.begin() as conn:
            await conn.execute(text("DELETE FROM usage_ledger WHERE request_id LIKE 'rq-rls-m43-%'"))


async def test_mock_claim_replay_cross_tenant_is_loud_under_rls(mock_rls_seeded, mock_rls_engine) -> None:
    """观察 ㉚ 的证人：`_claim_and_execute` 回放分支 SELECT 不带租户过滤（app.py:104，
    与 claim 的 INSERT 不对称）——"RLS 第二层由调用侧环境承担"这句 docstring 首次有 CI 作证。

    跨租撞键（A 上下文撞 B 的既有键）：唯一索引仲裁发生在存储层不看 RLS（claim
    rowcount=0 照样成立），随后的回放读被 RLS 拦成空集 → scalar_one 响亮
    NoResultFound（ASGITransport 默认让根因裸穿；生产端点面即 500）——绝不静默
    借用 B 的结果快照。同租撞键回放 duplicate:true 健康如常。幂等键一旦改成
    业务可控值（订单号+操作类型），跨租撞键就从"不可构造"变成常态路径——
    届时本条的期望要按 ㉚ 修向（补租户过滤）重审。
    """
    import httpx
    from sqlalchemy.exc import NoResultFound
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from aegis.apps.support.mock_backend.app import create_mock_api
    from aegis.core.config import Settings

    owner = mock_rls_seeded
    async with owner.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO mock_write_ops (idempotency_key, kind, tenant_id, payload) "
                "VALUES ('wo-rls-claim-b', 'refund', 'rls-t-b', CAST(:p AS jsonb))"
            ),
            {"p": json.dumps({"order_id": "mo-rls-b", "status": "refunded"})},
        )
    app = create_mock_api(
        settings=Settings(), session_factory=async_sessionmaker(mock_rls_engine, expire_on_commit=False)
    )
    body = {"tenant_id": "rls-t-a", "user_id": "u-rls", "order_id": "mo-rls-a", "amount": "1.00"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock") as c:
        with tenant_context("rls-t-a"):
            with pytest.raises(NoResultFound):  # 撞 B 键：响亮炸，不借用
                await c.post("/refunds", json=body, headers={"Idempotency-Key": "wo-rls-claim-b"})
            first = await c.post("/refunds", json=body, headers={"Idempotency-Key": "wo-rls-claim-a"})
            assert first.status_code == 200
            assert first.json()["duplicate"] is False
            again = await c.post("/refunds", json=body, headers={"Idempotency-Key": "wo-rls-claim-a"})
            assert again.status_code == 200
            assert again.json()["duplicate"] is True  # 同租回放：RLS 在场时健康如常


# ---------------------------------------------------------------------------
# M4.4 增量节：评测双表的 RLS 前置义务证人
# ---------------------------------------------------------------------------
# M3.3 前置义务：新表迁移必须自带 ENABLE RLS + 策略（DEFAULT PRIVILEGES 只授 DML
# 不给 RLS）。eval_cases 带 tenant_id 列 → 按 P5 口径入 RLS 名单（第十表）；
# eval_runs 无 tenant_id 列 → 不上（events 先例）。本条与 rag/mock 的
# "policies in place" 同款——迁移漏写策略时在这里红，而不是等某天 app 引擎
# 静默读空集。


async def test_eval_cases_rls_policy_in_place(owner_engine) -> None:
    async with owner_engine.connect() as conn:
        ok = (await conn.execute(text("SELECT to_regclass('eval_cases') IS NOT NULL"))).scalar_one()
        if not ok:
            if os.environ.get("CI"):
                raise RuntimeError("CI 里 eval_cases 必须在位——检查 M4.4 迁移是否入链")
            pytest.skip("eval_cases 未建：先 uv run alembic upgrade head")
        n = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM pg_policies "
                    "WHERE tablename = 'eval_cases' AND policyname = 'tenant_isolation'"
                )
            )
        ).scalar_one()
    assert n == 1

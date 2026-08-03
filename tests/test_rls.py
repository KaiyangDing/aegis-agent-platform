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

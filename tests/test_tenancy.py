"""M3.1 交付①：业务底座两表 + TenantDirectory 只读目录（60s TTL 缓存——#22 拍板）。

缓存断言全部注入 clock，不做真实计时（00 §2.2 时序纪律）；DB 断言开新会话
re-select，不信内存对象（server_default 列以库为准）。
"""

from __future__ import annotations

from sqlalchemy import select

from aegis.core.tenancy import Role, TenantDirectory, TenantRecord, UserRecord


class _FakeClock:
    """可拨动的单调钟：now 手动前进，缓存过期测试与真实时间无关。"""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _CountingFactory:
    """包一层会话工厂并数开启次数——"缓存命中不回库"的判据（开会话数即回库数）。"""

    def __init__(self, factory) -> None:
        self._factory = factory
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self._factory()


async def _seed(factory, *, tid: str = "t-dir", uid: str = "u-dir", budget: int = 1_000_000) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(
                TenantRecord(id=tid, name="测试租户", config={"approval_threshold": 200}, token_budget_monthly=budget)
            )
            s.add(UserRecord(id=uid, tenant_id=tid, role=Role.OPERATOR.value, display_name="测试坐席"))


def test_role_values_are_stable() -> None:
    """三档值快照：进 users.role 列与 JWT claims（交付②），改值=破坏在途 token 与历史行。"""
    assert {r.value for r in Role} == {"user", "operator", "admin"}
    assert len(Role) == 3


async def test_tenant_row_roundtrip(db_session_factory) -> None:
    """config JSONB 原样往返；created_at/updated_at 由 DB 钟赋值（server_default）。"""
    await _seed(db_session_factory, tid="t-rt", uid="u-rt")
    async with db_session_factory() as s:
        row = (await s.execute(select(TenantRecord).where(TenantRecord.id == "t-rt"))).scalar_one()
    assert row.config == {"approval_threshold": 200}
    assert row.token_budget_monthly == 1_000_000
    assert row.created_at is not None and row.updated_at is not None


async def test_user_display_name_defaults_empty(db_session_factory) -> None:
    """display_name 的 default 在 ORM 层——种子/夹具走 ORM 才生效（裸 SQL 必须显式给全列）。"""
    async with db_session_factory() as s:
        async with s.begin():
            s.add(UserRecord(id="u-min", tenant_id="t-x", role=Role.USER.value))
    async with db_session_factory() as s:
        row = (await s.execute(select(UserRecord).where(UserRecord.id == "u-min"))).scalar_one()
    assert row.display_name == ""
    assert row.role == Role.USER


async def test_directory_returns_seeded_rows(db_session_factory) -> None:
    await _seed(db_session_factory)
    directory = TenantDirectory(db_session_factory, clock=_FakeClock())
    tenant = await directory.get_tenant("t-dir")
    user = await directory.get_user("u-dir")
    assert tenant is not None and tenant.name == "测试租户"
    assert user is not None and user.role == Role.OPERATOR
    assert await directory.monthly_budget("t-dir") == 1_000_000


async def test_directory_unknown_ids(db_session_factory) -> None:
    """未知租户预算 0 = 闸门关闭——与 Settings.tenant_monthly_token_budget 默认 0 同语义（P3 不变量）。"""
    directory = TenantDirectory(db_session_factory, clock=_FakeClock())
    assert await directory.get_tenant("t-ghost") is None
    assert await directory.get_user("u-ghost") is None
    assert await directory.monthly_budget("t-ghost") == 0


async def test_cache_hit_skips_db_within_ttl(db_session_factory) -> None:
    await _seed(db_session_factory, tid="t-hit", uid="u-hit")
    counting = _CountingFactory(db_session_factory)
    clock = _FakeClock()
    directory = TenantDirectory(counting, cache_ttl_s=60.0, clock=clock)
    first = await directory.get_tenant("t-hit")
    clock.now = 59.9  # TTL 窗内
    second = await directory.get_tenant("t-hit")
    assert counting.calls == 1  # 第二次纯缓存命中，未开会话
    assert second is first


async def test_cache_expires_after_ttl(db_session_factory) -> None:
    await _seed(db_session_factory, tid="t-exp", uid="u-exp")
    counting = _CountingFactory(db_session_factory)
    clock = _FakeClock()
    directory = TenantDirectory(counting, cache_ttl_s=60.0, clock=clock)
    await directory.get_tenant("t-exp")
    clock.now = 60.0  # 到界即过期（clock < 截止时刻才命中）
    await directory.get_tenant("t-exp")
    assert counting.calls == 2


async def test_miss_is_not_negatively_cached(db_session_factory) -> None:
    """miss 不入缓存：新种子的租户不被 60s 负缓存误伤（认证 401 面——设计注记见 tenancy.py）。"""
    counting = _CountingFactory(db_session_factory)
    clock = _FakeClock()
    directory = TenantDirectory(counting, cache_ttl_s=60.0, clock=clock)
    assert await directory.get_tenant("t-late") is None
    assert await directory.get_tenant("t-late") is None
    assert counting.calls == 2  # 两次 miss 两次回库
    await _seed(db_session_factory, tid="t-late", uid="u-late")
    found = await directory.get_tenant("t-late")
    assert found is not None and found.id == "t-late"

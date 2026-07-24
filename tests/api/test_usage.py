"""M3.1 交付④：GET /v1/usage——矩阵（user 403/operator 锁本租户/admin 平台级）+ 聚合对账。

种子经 ORM 写 usage_ledger（SAVEPOINT 夹具，零污染）；端点经 app.state.session_factory
注入同一夹具工厂，查询与种子同一事务视界。金额在 JSON 里是精确小数字符串
（pydantic v2 对 Decimal 的缺省序列化——"钱不过 float"口径延伸到线上表示），断言用 Decimal。
"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from aegis.api.auth import issue_token
from aegis.api.main import create_app
from aegis.core.config import Settings
from aegis.core.tenancy import Role
from aegis.core.tenant_ctx import current_tenant_id
from aegis.gateway.metering import UsageRecord

SECRET = "usage-test-secret-0123456789abcdef"  # ≥32B（RFC 7518 下限）


def _token(role: Role, uid: str, tid: str = "tenant-a") -> str:
    return issue_token(user_id=uid, tenant_id=tid, role=role, ttl_s=3600, secret=SECRET)


def _bearer(role: Role, uid: str, tid: str = "tenant-a") -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(role, uid, tid)}"}


async def _seed_usage(factory) -> None:
    """tenant-a 两行（m-alpha 真调用 + m-beta 缓存命中零成本）、tenant-b 一行。"""
    async with factory() as s:
        async with s.begin():
            s.add(
                UsageRecord(
                    request_id="r-a1",
                    tenant_id="tenant-a",
                    session_id="s-a1",
                    tier="standard",
                    provider="bailian",
                    model="m-alpha",
                    prompt_tokens=100,
                    completion_tokens=50,
                    cached=False,
                    cost=Decimal("0.100000"),
                )
            )
            s.add(
                UsageRecord(
                    request_id="r-a2",
                    tenant_id="tenant-a",
                    session_id="s-a1",
                    tier="fast",
                    provider="cache",
                    model="m-beta",
                    prompt_tokens=10,
                    completion_tokens=5,
                    cached=True,
                    cost=Decimal("0"),
                )
            )
            s.add(
                UsageRecord(
                    request_id="r-b1",
                    tenant_id="tenant-b",
                    session_id="s-b1",
                    tier="standard",
                    provider="bailian",
                    model="m-alpha",
                    prompt_tokens=7,
                    completion_tokens=3,
                    cached=False,
                    cost=Decimal("0.007000"),
                )
            )


@pytest.fixture
async def client(db_session_factory):
    app = create_app(
        Settings(jwt_secret=SecretStr(SECRET)),
        session_factory=db_session_factory,
    )
    await _seed_usage(db_session_factory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_missing_token_401(client) -> None:
    assert (await client.get("/v1/usage")).status_code == 401


async def test_user_role_403(client) -> None:
    """矩阵行：终端用户不可见成本视图（02 §7.1）。"""
    resp = await client.get("/v1/usage", headers=_bearer(Role.USER, "u-a1"))
    assert resp.status_code == 403


async def test_operator_sees_only_own_tenant(client) -> None:
    resp = await client.get("/v1/usage", headers=_bearer(Role.OPERATOR, "op-a1"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == "tenant-a"
    assert {r["request_id"] for r in body["detail"]} == {"r-a1", "r-a2"}  # r-b1 不可见


async def test_operator_foreign_tenant_param_403(client) -> None:
    """强制过滤的显式面：operator 点名他租 → 403 而非静默改写（审计口径清晰）。"""
    resp = await client.get("/v1/usage?tenant_id=tenant-b", headers=_bearer(Role.OPERATOR, "op-a1"))
    assert resp.status_code == 403


async def test_admin_defaults_own_and_queries_other(client) -> None:
    """admin 平台级：缺省看自己 token 的租户，点名可查任意租户（矩阵 ✅ 无限定）。"""
    own = (await client.get("/v1/usage", headers=_bearer(Role.ADMIN, "admin-a1"))).json()
    assert own["tenant_id"] == "tenant-a"
    other = await client.get("/v1/usage?tenant_id=tenant-b", headers=_bearer(Role.ADMIN, "admin-a1"))
    assert other.status_code == 200
    body = other.json()
    assert body["tenant_id"] == "tenant-b"
    assert [r["request_id"] for r in body["detail"]] == ["r-b1"]


async def test_aggregates_match_seeded_rows(client) -> None:
    """聚合与预置行逐项对账（02 §9：聚合=模型/天/会话；缓存命中计次不计钱）。"""
    body = (await client.get("/v1/usage", headers=_bearer(Role.OPERATOR, "op-a1"))).json()
    by_model = {r["model"]: r for r in body["by_model"]}
    assert by_model["m-alpha"]["calls"] == 1 and by_model["m-alpha"]["tokens"] == 150
    # 金额是精确小数字符串（pydantic v2 对 Decimal 的 JSON 缺省）——Decimal 比较，精度无损
    assert Decimal(by_model["m-alpha"]["cost"]) == Decimal("0.1")
    assert by_model["m-beta"]["cache_hits"] == 1 and Decimal(by_model["m-beta"]["cost"]) == 0
    assert len(body["by_day"]) == 1 and body["by_day"][0]["calls"] == 2  # 种子同日（DB 钟）
    (sess,) = body["by_session"]
    assert sess["session_id"] == "s-a1" and sess["tokens"] == 165


async def test_limit_caps_detail_newest_first(client) -> None:
    body = (await client.get("/v1/usage?limit=1", headers=_bearer(Role.OPERATOR, "op-a1"))).json()
    assert [r["request_id"] for r in body["detail"]] == ["r-a2"]  # 同钟按 id 兜底降序=最新一行


class _CtxRecordingFactory:
    """记录每次开会话时的租户上下文——"以目标租户身份查库"的判据（M3.3② 接线）。"""

    def __init__(self, factory) -> None:
        self._factory = factory
        self.seen: list[str | None] = []

    def __call__(self):
        self.seen.append(current_tenant_id.get())
        return self._factory()


async def test_usage_queries_run_in_target_tenant_context(db_session_factory) -> None:
    """admin 点名他租时四条查询全在目标租户上下文内跑——RLS 下跨租户视图的前提；
    认证层设的是 admin 自家租户，端点须用 tenant_context(target) 嵌套覆盖（M3.3②）。"""
    recording = _CtxRecordingFactory(db_session_factory)
    app = create_app(Settings(jwt_secret=SecretStr(SECRET)), session_factory=recording)
    await _seed_usage(db_session_factory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/v1/usage?tenant_id=tenant-b", headers=_bearer(Role.ADMIN, "admin-a1"))
    assert resp.status_code == 200
    # 端点开一个会话跑四条查询（factory 恰调一次）；开会话时刻已戴目标租户的牌=
    # tenant_context(target) 覆盖了认证层的 tenant-a（首版断言误设四次开会话——测试稿缺陷）
    assert recording.seen == ["tenant-b"]

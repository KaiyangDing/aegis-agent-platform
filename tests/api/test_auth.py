"""M3.1 交付②：JWT 签发/验签（双密钥窗/过期/坏签名/alg 混淆/空密钥）+ 端点矩阵依赖（401/403 分工）。

过期用注入 now 构造"1970 年签发的票"，不做真实等待（00 §2.2 时序纪律）；
端点测试 httpx ASGITransport 驱动 create_app 实例，零网络零真实调用。
Settings 显式传全部被消费字段——.env 存在与否都不影响断言（不引 make_settings：
其 type: ignore 是全仓唯一豁免点，不为测试便利再开第二处）。
"""

from __future__ import annotations

from typing import Annotated

import httpx
import jwt as pyjwt
import pytest
from fastapi import Depends, FastAPI
from pydantic import SecretStr

from aegis.api.auth import (
    InvalidToken,
    Principal,
    current_principal,
    decode_token,
    issue_token,
    require_roles,
)
from aegis.api.main import create_app
from aegis.core.config import Settings
from aegis.core.tenancy import Role

# ≥32 字节（RFC 7518 HS256 硬下限，auth.py 升为 ValueError）——短钥既触
# PyJWT InsecureKeyLengthWarning 也过不了我们的配置检查
CURRENT = "unit-test-current-secret-0123456789ab"
PREVIOUS = "unit-test-previous-secret-0123456789a"
FAR_FUTURE = 33_000_000_000  # ≈ 公元 3015 年：手工伪造 claims 用的不过期 exp


def _settings() -> Settings:
    return Settings(jwt_secret=SecretStr(CURRENT), jwt_secret_previous=SecretStr(PREVIOUS))


def _token(role: Role = Role.USER, *, secret: str = CURRENT, ttl_s: int = 3600, uid: str = "u-a1") -> str:
    return issue_token(user_id=uid, tenant_id="tenant-a", role=role, ttl_s=ttl_s, secret=secret)


def _stale_token() -> str:
    # 1970 年签发的 60s 票——过期判定交给 PyJWT 对真实时钟，余量五十余年，零时序敏感
    return issue_token(user_id="u", tenant_id="t", role=Role.USER, ttl_s=60, secret=CURRENT, now=lambda: 1_000_000)


# ---- 纯函数层 ----


def test_issue_decode_roundtrip() -> None:
    principal = decode_token(_token(Role.OPERATOR, uid="op-a1"), secret=CURRENT)
    assert principal == Principal(user_id="op-a1", tenant_id="tenant-a", role=Role.OPERATOR)


def test_expired_token_rejected() -> None:
    with pytest.raises(InvalidToken):
        decode_token(_stale_token(), secret=CURRENT)


def test_bad_signature_rejected() -> None:
    with pytest.raises(InvalidToken):
        decode_token(_token(secret="wrong-secret-0123456789abcdefghijklm"), secret=CURRENT, previous="")


def test_previous_secret_window() -> None:
    """轮换窗（P2）：旧钥签的在途票在窗内仍认；窗关（previous 清空）即拒。"""
    old = _token(secret=PREVIOUS)
    assert decode_token(old, secret=CURRENT, previous=PREVIOUS).user_id == "u-a1"
    with pytest.raises(InvalidToken):
        decode_token(old, secret=CURRENT)


def test_empty_secret_is_config_error_not_401() -> None:
    """空密钥=服务端错配，fail-loud ValueError——绝不装作"客户端 token 不对"混进 401。"""
    with pytest.raises(ValueError):
        issue_token(user_id="u", tenant_id="t", role=Role.USER, ttl_s=60, secret="")
    with pytest.raises(ValueError):
        decode_token("whatever", secret="")


def test_short_secret_is_config_error() -> None:
    """RFC 7518 HS256 下限（32 字节）升为硬错误：弱钥=配置 bug fail-loud，不靠库告警苟活。"""
    with pytest.raises(ValueError):
        issue_token(user_id="u", tenant_id="t", role=Role.USER, ttl_s=60, secret="dev123")
    with pytest.raises(ValueError):
        decode_token("whatever", secret="dev123")
    with pytest.raises(ValueError):
        decode_token("whatever", secret=CURRENT, previous="short-previous")


def test_alg_none_rejected() -> None:
    """alg 混淆第一攻击面：无签名 token 必须被显式 algorithms=["HS256"] 挡下。"""
    unsigned = pyjwt.encode({"sub": "u", "tid": "t", "role": "admin", "exp": FAR_FUTURE}, "", algorithm="none")
    with pytest.raises(InvalidToken):
        decode_token(unsigned, secret=CURRENT)


def test_unknown_role_claim_rejected() -> None:
    forged = pyjwt.encode({"sub": "u", "tid": "t", "role": "root", "exp": FAR_FUTURE}, CURRENT, algorithm="HS256")
    with pytest.raises(InvalidToken):
        decode_token(forged, secret=CURRENT)


def test_missing_claim_rejected() -> None:
    """require 清单（exp/sub/tid/role）缺一即拒——没有 exp 的票是永不过期票，不许进门。"""
    partial = pyjwt.encode({"sub": "u", "exp": FAR_FUTURE}, CURRENT, algorithm="HS256")
    with pytest.raises(InvalidToken):
        decode_token(partial, secret=CURRENT)


# ---- 端点层（矩阵执行器）----

_STAFF_ONLY = require_roles(Role.OPERATOR, Role.ADMIN)


def _build_app() -> FastAPI:
    app = create_app(_settings())

    @app.get("/whoami")
    async def whoami(principal: Annotated[Principal, Depends(current_principal)]) -> dict[str, str]:
        return {"user_id": principal.user_id, "tenant_id": principal.tenant_id, "role": principal.role.value}

    @app.get("/staff-only")
    async def staff_only(principal: Annotated[Principal, Depends(_STAFF_ONLY)]) -> dict[str, str]:
        return {"user_id": principal.user_id}

    return app


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_build_app()), base_url="http://test") as c:
        yield c


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_healthz_open(client) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200 and resp.json() == {"status": "ok"}


async def test_missing_token_401(client) -> None:
    resp = await client.get("/whoami")
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


async def test_malformed_scheme_401(client) -> None:
    resp = await client.get("/whoami", headers={"Authorization": f"Token {_token()}"})
    assert resp.status_code == 401


async def test_valid_token_returns_identity(client) -> None:
    resp = await client.get("/whoami", headers=_bearer(_token(Role.USER, uid="u-a1")))
    assert resp.status_code == 200
    assert resp.json() == {"user_id": "u-a1", "tenant_id": "tenant-a", "role": "user"}


async def test_expired_token_401_at_endpoint(client) -> None:
    resp = await client.get("/whoami", headers=_bearer(_stale_token()))
    assert resp.status_code == 401


async def test_user_role_403_on_staff_endpoint(client) -> None:
    """401/403 分工不变量的前半：身份合法但角色不符=403（M3.2 补 404/409/429 的后半）。"""
    resp = await client.get("/staff-only", headers=_bearer(_token(Role.USER)))
    assert resp.status_code == 403


async def test_operator_and_admin_pass_staff_endpoint(client) -> None:
    for role, uid in ((Role.OPERATOR, "op-a1"), (Role.ADMIN, "admin-a1")):
        resp = await client.get("/staff-only", headers=_bearer(_token(role, uid=uid)))
        assert resp.status_code == 200, role
        assert resp.json() == {"user_id": uid}

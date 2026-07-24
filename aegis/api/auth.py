"""JWT 认证与 RBAC 依赖（M3.1 交付②，02 §7.1 / P2 拍板）。

凭证形态：终端用户与坐席/管理员同为 HS256 短期 JWT（claims: sub/tid/role/iat/exp），
差别只在 TTL（user 2h / staff 8h）与发放形态（P7：scripts/mint_token.py，v1 无登录端点）。
密钥托管：Settings.jwt_secret（SecretStr，环境变量 JWT_SECRET）；轮换=双密钥窗——
验签先试 current、仅签名不符再试 previous，轮换不踢在线用户。
失败分层：空密钥=配置 bug，ValueError fail-loud（不许混进 401 掩盖服务端错配）；
token 验证失败=客户端问题，InvalidToken → 依赖层映射 401。
矩阵执行器 = require_roles 依赖工厂：端点用 Annotated 声明角色面，handler 体内零散 if。
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status

from aegis.core.config import Settings
from aegis.core.tenancy import Role
from aegis.core.tenant_ctx import current_tenant_id

_ALGORITHM = "HS256"
_REQUIRED_CLAIMS = ["exp", "sub", "tid", "role"]
"""decode 必须显式锁 algorithms 且强制 claim 清单——PyJWT 为兼容默认不强制，
alg 混淆（none/换头）是 JWT 第一攻击面；缺 exp 的票=永不过期票，一并拒收。"""
_MIN_SECRET_BYTES = 32
"""HS256 密钥硬下限（RFC 7518 §3.2：MUST ≥256 bit）。PyJWT 对短钥只发
InsecureKeyLengthWarning——按"配置错误启动时炸"口径升为硬错误，
弱钥不许进入任何签发/验签路径。"""


def _check_secret(secret: str, *, name: str) -> None:
    if not secret:
        raise ValueError(f"{name} 未配置——空密钥上不许签发/验签（.env 设 JWT_SECRET，P2）")
    if len(secret.encode("utf-8")) < _MIN_SECRET_BYTES:
        raise ValueError(
            f"{name} 不足 {_MIN_SECRET_BYTES} 字节（RFC 7518 HS256 下限）——用 secrets.token_urlsafe(32) 生成合规密钥"
        )


class InvalidToken(Exception):
    """token 验证失败（签名/过期/claims 缺失/角色非法）——依赖层映射 401。

    与 ValueError（空密钥=服务端配置 bug，fail-loud 不映射 401）刻意分家。
    """


def _epoch_now() -> int:
    return int(time.time())


@dataclass(frozen=True, slots=True)
class Principal:
    """一次请求的已验证身份：端点矩阵与归属校验（#19）的唯一输入。"""

    user_id: str
    tenant_id: str
    role: Role


def issue_token(
    *,
    user_id: str,
    tenant_id: str,
    role: Role,
    ttl_s: int,
    secret: str,
    now: Callable[[], int] = _epoch_now,
) -> str:
    """签发 HS256 JWT。now 可注入：过期测试构造旧票，不做真实等待（00 §2.2 时序纪律）。"""
    _check_secret(secret, name="jwt_secret")
    if not user_id or not tenant_id:
        raise ValueError("user_id/tenant_id 不许为空——身份三元组是矩阵与归属校验的根")
    iat = now()
    claims = {"sub": user_id, "tid": tenant_id, "role": role.value, "iat": iat, "exp": iat + ttl_s}
    return jwt.encode(claims, secret, algorithm=_ALGORITHM)


def _principal_from_claims(claims: dict[str, Any]) -> Principal:
    try:
        sub, tid, role_raw = claims["sub"], claims["tid"], claims["role"]
    except KeyError as e:  # require 清单已拦；此为清单日后漂移的兜底
        raise InvalidToken(f"token 缺少必要 claim：{e}") from e
    try:
        role = Role(role_raw)
    except ValueError as e:
        raise InvalidToken(f"token 角色非法：{role_raw!r}") from e
    return Principal(user_id=sub, tenant_id=tid, role=role)


def decode_token(token: str, *, secret: str, previous: str = "") -> Principal:
    """验签并提取身份。双密钥窗（P2）：仅"签名不符"才试 previous——
    过期/格式坏换哪把钥匙都救不回来，直接失败不白试。"""
    _check_secret(secret, name="jwt_secret")
    if previous:
        _check_secret(previous, name="jwt_secret_previous")
    signature_mismatch = False
    for key in (secret, previous):
        if not key:
            continue
        try:
            claims = jwt.decode(token, key, algorithms=[_ALGORITHM], options={"require": _REQUIRED_CLAIMS})
        except jwt.InvalidSignatureError:
            signature_mismatch = True
            continue
        except jwt.PyJWTError as e:
            # 只回显异常类型名不回显 token 内容（源头打码纪律）
            raise InvalidToken(f"token 无效：{type(e).__name__}") from e
        return _principal_from_claims(claims)
    if signature_mismatch:
        raise InvalidToken("token 签名不符（current 与 previous 均不匹配）")
    raise InvalidToken("token 无效")


async def current_principal(request: Request) -> Principal:
    """FastAPI 依赖：解析 Authorization: Bearer 头。401 三态：缺头/格式错/验签失败。"""
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少或格式错误的 Authorization: Bearer 凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings: Settings = request.app.state.settings
    try:
        principal = decode_token(
            token.strip(),
            secret=settings.jwt_secret.get_secret_value(),
            previous=settings.jwt_secret_previous.get_secret_value(),
        )
    except InvalidToken as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    # M3.3②（#18 请求路径）：验签即设租户上下文——RLS 事务钩子从此有值可抄。
    # 只 set 不 reset：ContextVar 随本请求任务生灭，任务结束即消散，不会泄给下个请求
    current_tenant_id.set(principal.tenant_id)
    return principal


def require_roles(*roles: Role) -> Callable[..., Awaitable[Principal]]:
    """依赖工厂：端点×角色矩阵（02 §7.1）的执行器。

    用法：principal: Annotated[Principal, Depends(require_roles(Role.OPERATOR, Role.ADMIN))]。
    角色不符 → 403——"身份合法但无权"与 401"身份无效"严格分家（状态码分工不变量）。
    """
    allowed = frozenset(roles)

    async def dependency(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前角色无权访问该端点")
        return principal

    return dependency

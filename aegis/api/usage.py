"""GET /v1/usage：租户成本视图（M3.1 交付④，02 §9 / U13）。

口径：明细到请求 + 聚合（模型/天/会话）；报表走裸 SQL（00 §2.2：报表裸 SQL、
实体 ORM），列名以 gateway/metering.py 的 UsageRecord 为准。
矩阵（02 §7.1）：user ❌ / operator 仅本租户（点名他租显式 403）/ admin 平台级。
时间窗与分页 v1 不做：明细最近 limit 行、聚合全量——窗口参数归 M4.1 报表面。
金额：账本 Decimal；JSON 以精确小数字符串出线（pydantic v2 缺省序列化——
钱全链路不过 float，下游用 Decimal(str) 解析无损）。
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text

from aegis.api.auth import Principal, require_roles
from aegis.core.tenancy import Role
from aegis.core.tenant_ctx import tenant_context

router = APIRouter()

_STAFF = require_roles(Role.OPERATOR, Role.ADMIN)

_DETAIL_SQL = text("""
    SELECT request_id, session_id, tier, provider, model,
           prompt_tokens, completion_tokens, cached, cost, created_at
    FROM usage_ledger WHERE tenant_id = :tid
    ORDER BY created_at DESC, id DESC LIMIT :limit
""")
_BY_MODEL_SQL = text("""
    SELECT model, count(*) AS calls,
           sum(prompt_tokens + completion_tokens) AS tokens,
           sum(cost) AS cost,
           count(*) FILTER (WHERE cached) AS cache_hits
    FROM usage_ledger WHERE tenant_id = :tid GROUP BY model ORDER BY cost DESC, model
""")
_BY_DAY_SQL = text("""
    SELECT date_trunc('day', created_at)::date AS day, count(*) AS calls,
           sum(prompt_tokens + completion_tokens) AS tokens, sum(cost) AS cost
    FROM usage_ledger WHERE tenant_id = :tid GROUP BY 1 ORDER BY 1
""")
_BY_SESSION_SQL = text("""
    SELECT coalesce(session_id, '-') AS session_id, count(*) AS calls,
           sum(prompt_tokens + completion_tokens) AS tokens, sum(cost) AS cost
    FROM usage_ledger WHERE tenant_id = :tid
    GROUP BY 1 ORDER BY cost DESC, session_id LIMIT 20
""")


@router.get("/v1/usage")
async def get_usage(
    request: Request,
    principal: Annotated[Principal, Depends(_STAFF)],
    tenant_id: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict[str, Any]:
    """矩阵行执行：operator 锁本租户（点名他租 403，不静默改写——审计口径清晰）；
    admin 缺省看自己 token 的租户，点名可查任意租户。"""
    target = tenant_id or principal.tenant_id
    if principal.role is not Role.ADMIN and target != principal.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="operator 仅可查看本租户用量")
    factory = request.app.state.session_factory
    # M3.3②：以目标租户身份查库——tenant_context 嵌套覆盖认证层设的本租户；
    # 没有这层，RLS 会把 admin 的跨租户视图过滤成空集（operator 时 target≡本租户，语义不变）
    with tenant_context(target):
        async with factory() as s:
            detail = (await s.execute(_DETAIL_SQL, {"tid": target, "limit": limit})).mappings().all()
            by_model = (await s.execute(_BY_MODEL_SQL, {"tid": target})).mappings().all()
            by_day = (await s.execute(_BY_DAY_SQL, {"tid": target})).mappings().all()
            by_session = (await s.execute(_BY_SESSION_SQL, {"tid": target})).mappings().all()
    return {
        "tenant_id": target,
        "detail": [dict(r) for r in detail],
        "by_model": [dict(r) for r in by_model],
        "by_day": [dict(r) for r in by_day],
        "by_session": [dict(r) for r in by_session],
    }

"""GET /v1/sessions/{session_id}/events（M3.10③ 建骨架，M4.1② 升级为 trace 视图）。

矩阵：operator 限本租户（越界 403 点名=staff 面口径）、admin 平台级、user ❌
（trace 含 system prompt/内部工具名，开放即出口防护旁路）。
会话定位复用 approvals_lookup 平台查读缝（M3.9②：RLS 下 admin 跨租/403-404
判定需要平台视角）；事件与账本装配归 TraceAssembler（aegis/obs）——payload
一律过展示层 masker（02 §7.3"events 存原文、脱敏在展示层"在此兑现）。
响应=TraceView 全量装配（M4.1 拍板⑤）：after_seq/limit 已退役——全仓无
生产消费方（chat.html 走 /stream），演示规模全量可控；分页/增量导出 v2。
审计留痕=结构化日志一行（02 §7.3 最小落地；审计落表 v2）。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from aegis.api.auth import Principal, require_roles
from aegis.core.tenancy import Role, SessionFactory
from aegis.obs.trace import TraceAssembler, TraceView
from aegis.runtime.store import SessionRecord

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/v1/sessions/{session_id}/events")
async def session_events(
    session_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(require_roles(Role.OPERATOR, Role.ADMIN))],
) -> TraceView:
    factory: SessionFactory = request.app.state.session_factory
    lookup: SessionFactory = request.app.state.approvals_lookup
    async with lookup() as s:
        row = (await s.execute(select(SessionRecord).where(SessionRecord.id == session_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    if principal.role is Role.OPERATOR and principal.tenant_id != row.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能查看其他租户的会话")
    view = await TraceAssembler(factory).assemble(row)
    # 02 §7.3 审计最小落地：谁/什么角色/哪个租户/看了哪个会话/多少条——一行结构化留痕
    logger.info(
        "trace 访问：viewer=%s role=%s viewer_tenant=%s session=%s events=%d",
        principal.user_id,
        principal.role.value,
        principal.tenant_id,
        session_id,
        sum(len(run.events) for run in view.runs),
    )
    return view

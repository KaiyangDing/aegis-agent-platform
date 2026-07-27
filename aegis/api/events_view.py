"""GET /v1/sessions/{session_id}/events（M3.10③，U14——M4.1 trace API 底座）。

矩阵：operator 限本租户（越界 403 点名=staff 面口径）、admin 平台级、user ❌
（trace 含 system prompt/内部工具名，开放即出口防护旁路——§7 陷阱 12）。
会话定位复用 approvals_lookup 平台查读缝（M3.9②：RLS 下 admin 跨租/403-404
判定需要平台视角）；events 本体无 tenant_id 列不在 RLS 名单（P5）、经常规工厂读。
审计留痕=结构化日志一行（02 §7.3 最小落地；事件化/落表与 PII masker 归 M4.1）。
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from aegis.api.auth import Principal, require_roles
from aegis.core.tenancy import Role, SessionFactory
from aegis.runtime.store import EventRecord, SessionRecord

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_EVENTS = 1000
"""单次响应上限：trace 是调试面不是导出面（全量导出归 M4.1 再议）。"""


@router.get("/v1/sessions/{session_id}/events")
async def session_events(
    session_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(require_roles(Role.OPERATOR, Role.ADMIN))],
    after_seq: int = 0,
    limit: int = _MAX_EVENTS,
) -> dict[str, Any]:
    factory: SessionFactory = request.app.state.session_factory
    lookup: SessionFactory = request.app.state.approvals_lookup
    async with lookup() as s:
        row = (await s.execute(select(SessionRecord).where(SessionRecord.id == session_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    if principal.role is Role.OPERATOR and principal.tenant_id != row.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能查看其他租户的会话")
    async with factory() as s:
        rows = (
            await s.execute(
                select(EventRecord.id, EventRecord.run_id, EventRecord.seq, EventRecord.type, EventRecord.payload)
                .where(EventRecord.session_id == session_id, EventRecord.seq > after_seq)
                .order_by(EventRecord.seq)
                .limit(max(1, min(limit, _MAX_EVENTS)))
            )
        ).all()
    # 02 §7.3 审计最小落地：谁/什么角色/哪个租户/看了哪个会话/多少条——一行结构化留痕
    logger.info(
        "trace 访问：viewer=%s role=%s viewer_tenant=%s session=%s events=%d",
        principal.user_id,
        principal.role.value,
        principal.tenant_id,
        session_id,
        len(rows),
    )
    return {
        "session_id": session_id,
        "tenant_id": row.tenant_id,
        "events": [{"id": e.id, "run_id": e.run_id, "seq": e.seq, "type": e.type, "payload": e.payload} for e in rows],
    }

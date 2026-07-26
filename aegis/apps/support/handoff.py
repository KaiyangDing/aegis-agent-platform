"""转人工（M3.8 交付②，plans §4.8）：建工单 + 上下文摘要（ADR-007:38-39 v1 形态）。

摘要三档优先级：sessions.summary（M2.5 滚动摘要投影）→ 最近 3 条 messages 拼接
→ 固定占位（工单不许空 detail 地开出去）。handoff 事件由调用方（service 层持
EventWriter 者）写——单写者纪律，本函数不碰事件流。
计划签名的 summary 参数已删（偏差登记）：函数自己查库，参数即废。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from aegis.apps.support.mock_backend.client import mock_client
from aegis.core.tenancy import SessionFactory
from aegis.runtime.store import MessageRecord, SessionRecord


async def _session_summary(factory: SessionFactory, session_id: str) -> str:
    async with factory() as s:
        summary = (
            await s.execute(select(SessionRecord.summary).where(SessionRecord.id == session_id))
        ).scalar_one_or_none()
        if summary:
            return summary
        rows = (
            await s.execute(
                select(MessageRecord.role, MessageRecord.content)
                .where(MessageRecord.session_id == session_id)
                .order_by(MessageRecord.id.desc())
                .limit(3)
            )
        ).all()
    if not rows:
        return "（无历史消息）"
    return "\n".join(f"{r.role}: {r.content}" for r in reversed(rows))  # 倒查取近三条，再翻回时序正向


async def create_handoff(
    *, factory: SessionFactory, session_id: str, tenant_id: str, user_id: str, reason: str
) -> dict[str, Any]:
    """经 mock 工单系统建单，返回 {ticket_id, reason, summary}（handoff 事件 payload 的本体）。

    坐席拿到的是摘要不是全量事件流——完整轨迹凭 trace_id≡session_id 回查（X5，M4.1）。
    """
    summary = await _session_summary(factory, session_id)
    resp = await mock_client().post(
        "/tickets",
        json={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "title": f"[转人工] 会话 {session_id}（{reason}）",
            "detail": summary,
        },
    )
    resp.raise_for_status()
    ticket = resp.json()
    return {"ticket_id": ticket["ticket_id"], "reason": reason, "summary": summary}

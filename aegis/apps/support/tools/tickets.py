"""工单创建工具（M3.7 交付③，低危写显式豁免——C15 留档）。"""

from __future__ import annotations

from typing import Any

from aegis.apps.support.tools._shared import post_write
from aegis.runtime.tools import SideEffect, ToolContext, tool


# risk_exempt 理由（C15 要求豁免可审计）：建工单无资金面、无状态破坏面，
# 且 handoff（M3.8）依赖它无审批直通——挂闸门会让"转人工"卡在待人批的死锁里
@tool(side_effect=SideEffect.WRITE, risk_exempt=True)
async def ticket_create(ctx: ToolContext, title: str, detail: str = "") -> dict[str, Any]:
    """创建人工工单：用于投诉、复杂问题上报或需要人工跟进的事项。title 为标题，detail 为详情。"""
    resp = await post_write(
        "/tickets",
        json_body={"tenant_id": ctx.tenant_id, "user_id": ctx.user_id, "title": title, "detail": detail},
        idempotency_key=ctx.tool_call_id,  # 写工具一律带键（§4.7 不变量 2）；mock 工单台账暂不消费
    )
    resp.raise_for_status()
    out: dict[str, Any] = resp.json()
    return out

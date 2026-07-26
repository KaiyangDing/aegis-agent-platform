"""物流查询工具（M3.7 交付③，读形态）。"""

from __future__ import annotations

from typing import Any

from aegis.apps.support.mock_backend.client import mock_client
from aegis.apps.support.tools._shared import DENIED_TEXT, fetch_owned_order
from aegis.runtime.tools import SideEffect, ToolContext, tool


@tool(side_effect=SideEffect.READ)
async def logistics_query(ctx: ToolContext, order_id: str) -> dict[str, Any]:
    """查询订单的物流轨迹与当前配送状态。order_id 为订单号。"""
    # 先归属校验（与 order_query 同一底座、同一话术），过了才查轨迹
    order = await fetch_owned_order(ctx, order_id)
    if order is None:
        return {"error": DENIED_TEXT}
    resp = await mock_client().get(f"/logistics/{order_id}", params={"tenant_id": ctx.tenant_id})
    resp.raise_for_status()
    out: dict[str, Any] = resp.json()
    return out

"""订单查询工具（M3.7 交付③，读形态）。"""

from __future__ import annotations

from typing import Any

from aegis.apps.support.tools._shared import DENIED_TEXT, fetch_owned_order
from aegis.runtime.tools import SideEffect, ToolContext, tool


@tool(side_effect=SideEffect.READ)
async def order_query(ctx: ToolContext, order_id: str) -> dict[str, Any]:
    """查询订单详情：状态、实付金额、商品列表。order_id 为订单号。"""
    # docstring 是给模型的说明书（tools.py:148 机制）——机制注释一律写在这里：
    # 归属校验 fail-closed（对抗③）；回给模型的视图剔除 tenant_id/user_id 身份列
    order = await fetch_owned_order(ctx, order_id)
    if order is None:
        return {"error": DENIED_TEXT}
    return {
        "order_id": order["id"],
        "status": order["status"],
        "paid_amount": order["paid_amount"],
        "items": order["items"],
        "created_at": order["created_at"],
    }

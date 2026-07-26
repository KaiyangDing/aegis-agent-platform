"""优惠券补发工具（M3.7 交付③，写形态+风险闸门——复用退款骨架，租户 B 的写面主角）。"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from aegis.apps.support.tools._shared import DENIED_TEXT, fetch_owned_order, post_write
from aegis.runtime.tools import SideEffect, ToolContext, tool


def coupon_needs_approval(args: Any, tenant_config: Mapping[str, Any]) -> bool:
    """coupon_threshold 为 §4.7 新增租户 config 键（租户 B 侧 approval_threshold 对应物，
    种子值 M3.11 定）；缺省 0 = 任意正面额都挂审批——安全闸门 fail-closed 缺省。"""
    return bool(args.amount > tenant_config.get("coupon_threshold", 0))


@tool(side_effect=SideEffect.WRITE, risk_policy=coupon_needs_approval)
async def coupon_grant(ctx: ToolContext, order_id: str, amount: float) -> dict[str, Any]:
    """为订单补发优惠券。order_id 为订单号，amount 为面额（元）。面额超过阈值时需人工批准。"""
    dec = Decimal(str(amount))  # 与退款同款：float 进门立即定形
    order = await fetch_owned_order(ctx, order_id)
    if order is None:
        return {"error": DENIED_TEXT}
    resp = await post_write(
        "/coupons",
        json_body={"tenant_id": ctx.tenant_id, "user_id": ctx.user_id, "order_id": order_id, "amount": str(dec)},
        idempotency_key=ctx.tool_call_id,
    )
    if resp.status_code == 409:
        return {"error": resp.json().get("detail", "补发被业务系统拒绝")}
    resp.raise_for_status()
    out: dict[str, Any] = resp.json()
    return out

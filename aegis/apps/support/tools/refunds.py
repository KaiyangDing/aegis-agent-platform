"""退款工具（M3.7 交付③，写形态+风险闸门——两租户对抗与 HITL 演示的主角）。"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from aegis.apps.support.tools._shared import DENIED_TEXT, fetch_owned_order, post_write
from aegis.runtime.tools import SideEffect, ToolContext, tool


def refund_needs_approval(args: Any, tenant_config: Mapping[str, Any]) -> bool:
    """超过租户审批阈值挂 HITL（01 §5：200 是租户 A 的配置项不是平台常量）。
    谓词只看参数与租户策略——闸门里没有 ctx：归属是权限（handler 内 fail-closed），
    风险是闸门（放行但要人批），两道防线不混（§4.7 陷阱 3）。

    **缺省 0 = fail-closed**（M4.0② ㊲ 改判，原缺省 200）：租户 config 少这个键时
    语义是"任意正金额都要人批"，而不是"200 元以下静默直退"（无审批无告警无痕迹）。
    原缺省与 00 §2.2「安全闸门 fail-closed」直接冲突，且同族 `coupon_needs_approval`
    缺省 0 早就是这个方向——同类闸门对同一种故障（少一个键）给相反答案，而只有
    coupon 那条被论证过。可达性不低：#21 治理路径下"种子即初始化入口"，新租户漏配
    是现实运维事故。缺省不再冒充一个业务阈值：0 与"配了 200"不会被混为一谈。
    """
    return bool(args.amount > tenant_config.get("approval_threshold", 0))


@tool(side_effect=SideEffect.WRITE, risk_policy=refund_needs_approval)
async def refund_apply(ctx: ToolContext, order_id: str, amount: float) -> dict[str, Any]:
    """为订单发起退款。order_id 为订单号，amount 为退款金额（元）。金额超过审批阈值时需人工批准。"""
    dec = Decimal(str(amount))  # 陷阱 2：float 进门立即定形，钱不过 float——下游全程字符串
    order = await fetch_owned_order(ctx, order_id)
    if order is None:
        return {"error": DENIED_TEXT}
    resp = await post_write(
        "/refunds",
        json_body={"tenant_id": ctx.tenant_id, "user_id": ctx.user_id, "order_id": order_id, "amount": str(dec)},
        idempotency_key=ctx.tool_call_id,  # #6 闭环：write-ahead 事件 id 就是下游去重键
    )
    if resp.status_code == 409:
        # 业务拒绝（已退款/超可退上限）：dict 话术回填，不抛异常——不进连败账不禁用工具
        return {"error": resp.json().get("detail", "退款被业务系统拒绝")}
    resp.raise_for_status()
    out: dict[str, Any] = resp.json()
    return out

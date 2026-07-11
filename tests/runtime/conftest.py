"""runtime 子目录专属夹具：演示工具集。

运行时对"客服"一无所知（03 §1 依赖倒置）——测试用这套假业务工具排练注入：
一个读工具、一个带风险闸门的写工具、一个显式豁免的低危写工具。
M2.4 执行器、M2.6 回放、M2.7 总装的测试共用这一套道具。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from aegis.runtime.store import SessionRecord
from aegis.runtime.tools import SideEffect, ToolContext, ToolRegistry, tool


@tool(side_effect=SideEffect.READ)
async def demo_order_query(ctx: ToolContext, order_id: str) -> dict:
    """查询演示订单的状态与实付金额。"""
    return {"order_id": order_id, "status": "已发货", "paid": 350}


def _demo_refund_needs_approval(args: Any, tenant_config: Mapping[str, Any]) -> bool:
    return bool(args.amount > tenant_config.get("approval_threshold", 200))


@tool(side_effect=SideEffect.WRITE, risk_policy=_demo_refund_needs_approval)
async def demo_refund_apply(ctx: ToolContext, order_id: str, amount: int) -> dict:
    """为演示订单发起退款（超租户阈值走人工审批）。"""
    return {"refunded": amount, "idempotency_key": ctx.tool_call_id}


@tool(side_effect=SideEffect.WRITE, risk_exempt=True)
async def demo_ticket_create(ctx: ToolContext, title: str) -> dict:
    """创建演示工单（低危写：显式豁免审批）。"""
    return {"ticket": title, "by": ctx.user_id}


@pytest.fixture
def demo_registry() -> ToolRegistry:
    """每个测试一个全新注册表——测试之间不共享可变状态。"""
    return ToolRegistry([demo_order_query, demo_refund_apply, demo_ticket_create])


@pytest.fixture
def make_session(db_session_factory):
    """建 sessions 行的帮助协程（M2.7 P2 拍板：run 开头读行取身份，无行拒绝起跑）。

    M2 测试自建行；M3.2 起由 API 层建会话。摘要投影同样要求行先存在（store.py:261）。
    """

    async def _make(session_id: str, *, tenant_id: str = "t-a", user_id: str = "u-1") -> None:
        async with db_session_factory() as s:
            async with s.begin():
                s.add(SessionRecord(id=session_id, tenant_id=tenant_id, user_id=user_id))

    return _make

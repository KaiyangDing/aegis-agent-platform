"""工具五件真实链路验收三幕（M3.7④，demo_ 族；plans §4.7 验收栏）。

用法（仓库根执行——.env 相对 cwd 加载；PG/Redis 在、迁移到 head、种子已跑）：

    uv run python scripts/demo_tools_acceptance.py

幕 A（真实调用，成本 <¥0.01）：最小 AgentSpec（真网关 standard 档+四工具）跑
「查订单 mo-demo-a1 并退款 120 元」→ 期待 completed、工具序列含 order_query 与
refund_apply（120 < 阈值 200 不挂审批——HITL 闭环归 M3.9）。
幕 B（零 LLM）：同一幂等键二击 refund_apply.handler → 二击 duplicate=true（#6）。
幕 C（零 LLM）：A 租户用户二报用户一的订单退款 → 统一话术拒绝（对抗③实录）。

演示订单 upsert 自带（拍板Ⅲ：不动 seed_demo，M3.11 正式化）；finally 清理
mock 演示行（M2.10 教训：脚本残留污染断言）；会话/事件行保留（随机 id 零碰撞，
smoke_agent_real 同款）。计量与 RLS：main 自包 tenant_context（封闭名单第四处）。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from aegis.apps.support.mock_backend.models import MockOrderRecord
from aegis.apps.support.tools._shared import DENIED_TEXT
from aegis.apps.support.tools.logistics import logistics_query
from aegis.apps.support.tools.orders import order_query
from aegis.apps.support.tools.refunds import refund_apply
from aegis.apps.support.tools.tickets import ticket_create
from aegis.core.db import get_owner_session_factory, get_session_factory
from aegis.core.locks import build_session_lock
from aegis.core.tenant_ctx import tenant_context
from aegis.gateway.factory import build_gateway
from aegis.runtime.events import EventType
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec
from aegis.runtime.tools import ToolContext

TENANT = "tenant-a"
USER_ONE = "u-a1"
USER_TWO = "u-a2"

_SYSTEM = (
    "你是云杉数码商城的客服助手，用中文简洁回答。可用工具：order_query 查订单、"
    "logistics_query 查物流、refund_apply 退款、ticket_create 建工单。"
    "执行退款前先用 order_query 确认订单状态与金额。"
)

_ORDERS = [
    {"id": "mo-demo-a1", "user_id": USER_ONE, "amount": "300.00"},  # 幕 A：Agent 退款对象
    {"id": "mo-demo-a2", "user_id": USER_ONE, "amount": "300.00"},  # 幕 B/C：双击与对抗③对象
]


async def _seed_orders() -> None:
    """种子=维护面（owner，D4）；upsert 复跑即把状态重置回 paid——脚本可重复执行。"""
    async with get_owner_session_factory()() as s:
        async with s.begin():
            for o in _ORDERS:
                stmt = pg_insert(MockOrderRecord).values(
                    id=o["id"],
                    tenant_id=TENANT,
                    user_id=o["user_id"],
                    status="paid",
                    paid_amount=Decimal(o["amount"]),
                    items={"sku": "R68 Pro"},
                )
                await s.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[MockOrderRecord.id],
                        set_={"status": "paid", "user_id": stmt.excluded.user_id},
                    )
                )


async def _cleanup() -> None:
    async with get_owner_session_factory()() as s:
        async with s.begin():
            await s.execute(text("DELETE FROM mock_write_ops WHERE payload->>'order_id' LIKE 'mo-demo-%'"))
            await s.execute(text("DELETE FROM mock_orders WHERE id LIKE 'mo-demo-%'"))


async def _act_a() -> bool:
    session_id = f"s-m37-{uuid.uuid4().hex[:12]}"  # 随机会话 id：零碰撞（M2.11 教训）
    async with get_owner_session_factory()() as s:
        async with s.begin():
            await s.execute(
                text(
                    "INSERT INTO sessions (id, tenant_id, user_id, run_state, lease_generation, recovery_count) "
                    "VALUES (:s, :t, :u, 'idle', 0, 0)"
                ),
                {"s": session_id, "t": TENANT, "u": USER_ONE},
            )
    spec = AgentSpec(
        system_prompt=_SYSTEM,
        tools=(order_query, logistics_query, refund_apply, ticket_create),
        model_tier="standard",
        tenant_config={"approval_threshold": 200},
    )
    runtime = AgentRuntime(build_gateway(), get_session_factory(), lock=build_session_lock())
    tool_calls: list[str] = []
    reason = ""
    # 全量收流至自然终止（chat._drain 同款形态）：不提前 break 故无需 aclosing
    async for event in runtime.run(spec, session_id, "帮我查一下订单 mo-demo-a1 的状态，然后给它退款 120 元"):
        if event.type is EventType.TOOL_CALL:
            tool_calls.append(event.payload["tool_name"])
        if event.type is EventType.LOOP_TERMINATED:
            reason = event.payload["reason"]
    print(f"  终止原因={reason}  工具序列={tool_calls}  session={session_id}")
    ok = reason == "completed" and "order_query" in tool_calls and "refund_apply" in tool_calls
    print(f"  幕 A {'PASS' if ok else 'FAIL'}：completed 且工具序列含查单+退款")
    return ok


async def _act_b() -> bool:
    key = f"demo-dbl-{uuid.uuid4().hex[:8]}"
    ctx = ToolContext(tenant_id=TENANT, user_id=USER_ONE, session_id="s-demo-b", run_id="r-demo", tool_call_id=key)
    first = await refund_apply.handler(ctx, order_id="mo-demo-a2", amount=50.0)
    second = await refund_apply.handler(ctx, order_id="mo-demo-a2", amount=50.0)
    print(f"  首击 duplicate={first.get('duplicate')}  二击 duplicate={second.get('duplicate')}")
    ok = first.get("duplicate") is False and second.get("duplicate") is True
    print(f"  幕 B {'PASS' if ok else 'FAIL'}：双击恰一笔退款（#6 去重）")
    return ok


async def _act_c() -> bool:
    ctx = ToolContext(
        tenant_id=TENANT,
        user_id=USER_TWO,
        session_id="s-demo-c",
        run_id="r-demo",
        tool_call_id=f"demo-adv-{uuid.uuid4().hex[:8]}",
    )
    refund = await refund_apply.handler(ctx, order_id="mo-demo-a2", amount=10.0)
    query = await order_query.handler(ctx, order_id="mo-demo-a2")
    print(f"  越权退款响应={refund}")
    ok = refund == {"error": DENIED_TEXT} and query == {"error": DENIED_TEXT}
    print(f"  幕 C {'PASS' if ok else 'FAIL'}：他人订单读写均以统一话术拒绝（对抗③）")
    return ok


async def main() -> None:
    logging.basicConfig(level=logging.WARNING)  # fail-open 类 warning 必须可见
    with tenant_context(TENANT):  # 脚本 main 自包：RLS 与计量的身份宣告（封闭名单第四处）
        await _seed_orders()
        try:
            print("幕 A：真实 Agent 查单+退款")
            a = await _act_a()
            print("幕 B：双击去重")
            b = await _act_b()
            print("幕 C：对抗③（水平越权）")
            c = await _act_c()
            print(f"\n三幕汇总：{'全部 PASS' if a and b and c else '有 FAIL——把完整输出贴回排查'}")
        finally:
            await _cleanup()


if __name__ == "__main__":
    asyncio.run(main())

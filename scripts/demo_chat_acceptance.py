"""M3.8③ 完整客服链路真实验收三幕（demo_ 族；§4.8 验收栏 + FAQ 守卫实证）。

用法（仓库根执行——.env 相对 cwd 加载；PG/Redis 在、迁移到 head、**种子已按
M3.8③ 版重跑**（tenants.config 含 tools/faq——先 uv run python scripts/seed_demo.py））：

    uv run python scripts/demo_chat_acceptance.py

幕 A（真实，standard 档）：租户 A 全链——ChatService 走生产装配原件（create_app()
的 app.state.chat_service），「查订单 mo-svc-a1 并退款 80 元」→ completed、
tool_status 帧含 order_query 与 refund_apply、订单落库 refunded（80<阈值 200 直执）。
幕 B（真实，fast 档）：FAQ 守卫实证——同会话首问「你们几点营业？」→ faq_direct
（不起循环）；跟进问「一般要多久？」→ 守卫挡回主 Agent（reason=completed）。
幕 C（零 LLM）：工具面=攻击面——A 恰四件、B 恰二件（spec.tools 可证）。

预算：≈5 次 LLM 调用（fast×3+standard×2 上下），总成本 <¥0.02；
演示订单 upsert 自带+finally 清理；会话随机 id 保留（smoke 同款）；
每幕自包 tenant_context（脚本 main 形态，封闭名单第四处）。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from aegis.api.main import create_app
from aegis.apps.support.mock_backend.models import MockOrderRecord
from aegis.apps.support.service import ChatFrame, ChatService
from aegis.core.db import get_owner_session_factory
from aegis.core.tenant_ctx import tenant_context

TENANT_A = "tenant-a"
USER_A = "u-a1"


async def _seed_order() -> None:
    async with get_owner_session_factory()() as s:  # 种子=维护面（D4）；upsert 复跑即重置
        async with s.begin():
            stmt = pg_insert(MockOrderRecord).values(
                id="mo-svc-a1",
                tenant_id=TENANT_A,
                user_id=USER_A,
                status="paid",
                paid_amount=Decimal("300.00"),
                items={"sku": "R68 Pro"},
            )
            await s.execute(stmt.on_conflict_do_update(index_elements=[MockOrderRecord.id], set_={"status": "paid"}))


async def _new_session(sid: str, *, tenant: str = TENANT_A, user: str = USER_A) -> None:
    async with get_owner_session_factory()() as s:
        async with s.begin():
            await s.execute(
                text(
                    "INSERT INTO sessions (id, tenant_id, user_id, run_state, lease_generation, recovery_count) "
                    "VALUES (:s, :t, :u, 'idle', 0, 0)"
                ),
                {"s": sid, "t": tenant, "u": user},
            )


async def _cleanup() -> None:
    async with get_owner_session_factory()() as s:
        async with s.begin():
            await s.execute(text("DELETE FROM mock_write_ops WHERE payload->>'order_id' LIKE 'mo-svc-%'"))
            await s.execute(text("DELETE FROM mock_orders WHERE id LIKE 'mo-svc-%'"))


async def _handle(svc: ChatService, sid: str, message: str) -> list[ChatFrame]:
    return [f async for f in svc.handle(tenant_id=TENANT_A, user_id=USER_A, session_id=sid, message=message)]


def _done_reason(frames: list[ChatFrame]) -> str:
    return str(next((f.data["reason"] for f in reversed(frames) if f.kind == "done"), "（无 done 帧）"))


async def _act_a(svc: ChatService) -> bool:
    sid = f"s-m38-a-{uuid.uuid4().hex[:10]}"
    await _new_session(sid)
    frames = await _handle(svc, sid, "帮我查一下订单 mo-svc-a1 的状态，然后给它退款 80 元")
    tools = [f.data["tool_name"] for f in frames if f.kind == "tool_status"]
    reason = _done_reason(frames)
    async with get_owner_session_factory()() as s:
        status_now = (
            await s.execute(select(MockOrderRecord.status).where(MockOrderRecord.id == "mo-svc-a1"))
        ).scalar_one()
    reply = next((f.data["text"] for f in reversed(frames) if f.kind == "token"), None)
    print(f"  终止={reason}  工具序列={tools}  订单状态={status_now}  session={sid}")
    print(f"  答复：{reply}")
    ok = reason == "completed" and "order_query" in tools and "refund_apply" in tools and status_now == "refunded"
    print(f"  幕 A {'PASS' if ok else 'FAIL'}：全链查单+退款直执（80<200 不挂审批）")
    return ok


async def _act_b(svc: ChatService) -> bool:
    sid = f"s-m38-b-{uuid.uuid4().hex[:10]}"
    await _new_session(sid)
    first = await _handle(svc, sid, "你们几点营业？")
    r1 = _done_reason(first)
    reply1 = next((f.data["text"] for f in reversed(first) if f.kind == "token"), None)
    print(f"  首问 reason={r1}  答复：{reply1}")
    second = await _handle(svc, sid, "一般要多久？")
    r2 = _done_reason(second)
    print(f"  跟进问 reason={r2}（守卫应挡回主 Agent，绝不 faq_direct）")
    ok = r1 == "faq_direct" and r2 == "completed"
    print(f"  幕 B {'PASS' if ok else 'FAIL'}：首问直答、跟进问进主 Agent（M3.6 盲窗守卫实证）")
    return ok


async def _act_c(svc: ChatService) -> bool:
    # 每租户读各自配置前必须自声明身份（脚本=边界；跨租户动作每租户各包各的）：
    # tenants 表在 RLS 覆盖名单内，无上下文读=空集→合成空配置。首跑幕 C FAIL 实录：
    # B 面空集=RLS 第二防线正确拦截；A 面"正常"纯属 60s TTL 缓存残影（14h ③ 两课）
    with tenant_context("tenant-a"):
        spec_a = await svc.build_spec("tenant-a")
    with tenant_context("tenant-b"):
        spec_b = await svc.build_spec("tenant-b")
    names_a = [t.name for t in spec_a.tools]
    names_b = [t.name for t in spec_b.tools]
    print(f"  A 工具面={names_a}")
    print(f"  B 工具面={names_b}")
    ok = names_a == ["order_query", "logistics_query", "refund_apply", "ticket_create"] and names_b == [
        "order_query",
        "coupon_grant",
    ]
    print(f"  幕 C {'PASS' if ok else 'FAIL'}：工具面=攻击面，按租户白名单一个不多")
    return ok


async def main() -> None:
    logging.basicConfig(level=logging.WARNING)  # fail-open 类 warning 必须可见
    app = create_app()  # 生产装配原件：真网关+锁+检索接线+ChatService（组装在边缘）
    svc: ChatService = app.state.chat_service
    await _seed_order()
    try:
        with tenant_context(TENANT_A):
            print("幕 A：租户 A 全链（查单→退款 80 直执）")
            a = await _act_a(svc)
            print("幕 B：FAQ 守卫实证（首问直答/跟进问进主 Agent）")
            b = await _act_b(svc)
        print("幕 C：租户工具面")
        c = await _act_c(svc)
        print(f"\n三幕汇总：{'全部 PASS' if a and b and c else '有 FAIL——把完整输出贴回排查'}")
    finally:
        await _cleanup()


if __name__ == "__main__":
    asyncio.run(main())

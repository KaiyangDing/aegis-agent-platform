"""demo_hitl.ps1 的证据面帮手（M3.9 交付⑤）：种子/时钟注入/对账触发/状态取证。

四个子命令（在仓库根执行，.env 相对 cwd 加载）：
    uv run python scripts/demo_hitl_helper.py seed              # 演示订单就绪（upsert，复位 paid）
    uv run python scripts/demo_hitl_helper.py mark-refunded     # TOCTOU 制造：订单在"别处"被退掉
    uv run python scripts/demo_hitl_helper.py expire <aid>      # 时钟注入：审批单 expires_at 拨至 1h 前
    uv run python scripts/demo_hitl_helper.py sweep             # 直接调生产对账任务体（beat 每 60s 调同款）
    uv run python scripts/demo_hitl_helper.py status <sid>      # 会话/审批/事件/订单四面取证（owner 视角）

全部走 owner 维护面（D4）：种子与取证是平台职能不冒充租户；sweep 内部的恢复
本体自会在 tenant_context 内走 app 面（workers/hitl.py 身份纪律）。
输出键名（run_state=/status=/event_id=）是 demo_hitl.ps1 的断言匹配面，改动需同步。
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.dialects.postgresql import insert

from aegis.apps.support.mock_backend.models import MockOrderRecord, MockOrderStatus
from aegis.core.db import get_owner_session_factory
from aegis.runtime.store import ApprovalRecord, ApprovalStatus, EventRecord, SessionRecord

ORDER_ID = "HITL-DEMO-0001"
"""演示订单号：tenant-a / u-a1 / 实付 500——300 元退款必过 200 阈值挂审批。"""


async def seed() -> None:
    """upsert 演示订单并复位 paid（重跑即复位——B1 执行后订单变 refunded，后续段先跑本命令）。"""
    async with get_owner_session_factory()() as s:
        async with s.begin():
            stmt = insert(MockOrderRecord).values(
                id=ORDER_ID,
                tenant_id="tenant-a",
                user_id="u-a1",
                status=MockOrderStatus.PAID.value,
                paid_amount=Decimal("500.00"),
                items={"sku": "R68 Pro 演示机"},
            )
            await s.execute(
                stmt.on_conflict_do_update(
                    index_elements=[MockOrderRecord.id],
                    set_={
                        "tenant_id": stmt.excluded.tenant_id,
                        "user_id": stmt.excluded.user_id,
                        "status": stmt.excluded.status,
                        "paid_amount": stmt.excluded.paid_amount,
                    },
                )
            )
    print(f"订单就绪：{ORDER_ID}（tenant-a/u-a1，paid 500.00，status=paid）")


async def mark_refunded() -> None:
    """TOCTOU 剧情制造：批准落锤之前，订单在"另一个渠道"被退掉——#8 重跑要拦的就是这个。"""
    async with get_owner_session_factory()() as s:
        async with s.begin():
            await s.execute(
                update(MockOrderRecord)
                .where(MockOrderRecord.id == ORDER_ID)
                .values(status=MockOrderStatus.REFUNDED.value)
            )
    print(f"订单 {ORDER_ID} 已在别处退款（status=refunded）——审批仍挂着，就等它批下来")


async def expire(approval_id: str) -> None:
    """时钟注入（C7 哲学的演示面）：不等真实 24h，把 expires_at 拨到 1 小时前。"""
    async with get_owner_session_factory()() as s:
        async with s.begin():
            res = await s.execute(
                update(ApprovalRecord)
                .where(ApprovalRecord.id == approval_id, ApprovalRecord.status == ApprovalStatus.PENDING.value)
                .values(expires_at=datetime.now(UTC) - timedelta(hours=1))
            )
    if cast(CursorResult[Any], res).rowcount == 1:  # DML 运行时恒 CursorResult（store.py:193 同款）
        print(f"时钟注入：审批单 {approval_id} 的 expires_at 已拨至 1 小时前")
    else:
        print(f"未生效：审批单 {approval_id} 不在 pending（已被处理？）")


def sweep() -> None:
    """直接调生产任务体 expire_approvals()（celery task 直调即普通函数）——
    beat 每 approval_scan_interval_s=60s 触发同一函数，这里只是免等。"""
    from aegis.workers.hitl import expire_approvals

    report = expire_approvals()
    print(f"sweep 完成：expired={report['expired']} waiting={report['waiting']} kicked={report['kicked']}")


async def status(session_id: str) -> None:
    """四面取证：run_state / 审批单（含 event_id 审计链）/ 事件序列 / 演示订单。"""
    async with get_owner_session_factory()() as s:
        run_state = (
            await s.execute(select(SessionRecord.run_state).where(SessionRecord.id == session_id))
        ).scalar_one_or_none()
        approvals = (
            (
                await s.execute(
                    select(ApprovalRecord)
                    .where(ApprovalRecord.session_id == session_id)
                    .order_by(ApprovalRecord.created_at)
                )
            )
            .scalars()
            .all()
        )
        types = (
            (
                await s.execute(
                    select(EventRecord.type).where(EventRecord.session_id == session_id).order_by(EventRecord.seq)
                )
            )
            .scalars()
            .all()
        )
        order = (await s.execute(select(MockOrderRecord).where(MockOrderRecord.id == ORDER_ID))).scalar_one_or_none()
    print(f"session={session_id} run_state={run_state}")
    for a in approvals:
        print(f"approval id={a.id} status={a.status} operator={a.operator_id or '空'} event_id={a.event_id or '空'}")
    print("events: " + ",".join(types))
    if order is not None:
        print(f"order {ORDER_ID} status={order.status} paid={order.paid_amount}")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    if cmd == "seed":
        asyncio.run(seed())
    elif cmd == "mark-refunded":
        asyncio.run(mark_refunded())
    elif cmd == "expire" and len(sys.argv) == 3:
        asyncio.run(expire(sys.argv[2]))
    elif cmd == "sweep":
        sweep()
    elif cmd == "status" and len(sys.argv) == 3:
        asyncio.run(status(sys.argv[2]))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()

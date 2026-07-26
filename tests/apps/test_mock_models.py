"""M3.7 交付①：模拟业务两表 ORM——金额精度/状态值快照/JSONB 往返/幂等键主键冲突。

RLS/策略等迁移工件断言在 tests/test_rls.py 的 M3.7 增量节（真提交语义那边才看得见）；
本文件只管 ORM 语义（SAVEPOINT 夹具，owner 连接绕 RLS——test_rag_models 同款分工）。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from aegis.apps.support.mock_backend.models import (
    MockOrderRecord,
    MockOrderStatus,
    MockWriteOpRecord,
)


def test_order_status_values_are_stable() -> None:
    """四态值快照：status 列存 .value，可退性校验（交付② POST /refunds）按它分支——改值=破坏历史行。"""
    assert {s.value for s in MockOrderStatus} == {"paid", "shipped", "delivered", "refunded"}
    assert len(MockOrderStatus) == 4


async def test_order_roundtrip_money_stays_decimal(db_session_factory) -> None:
    """钱不过 float（M3.1④ 口径延伸到 mock 侧）：Numeric(12,2) 写 Decimal 读回 Decimal 精确等值。"""
    async with db_session_factory() as s:
        async with s.begin():
            s.add(
                MockOrderRecord(
                    id="mo-rt-1",
                    tenant_id="t-mock-rt",
                    user_id="u-mock-rt",
                    status=MockOrderStatus.PAID.value,
                    paid_amount=Decimal("199.99"),
                    items={"sku": "R68 Pro", "qty": 1},
                )
            )
    async with db_session_factory() as s:
        row = (await s.execute(select(MockOrderRecord).where(MockOrderRecord.id == "mo-rt-1"))).scalar_one()
    assert isinstance(row.paid_amount, Decimal)
    assert row.paid_amount == Decimal("199.99")
    assert row.items == {"sku": "R68 Pro", "qty": 1}
    assert row.status == "paid"
    assert row.created_at is not None


async def test_write_op_roundtrip(db_session_factory) -> None:
    """去重台账行往返：kind 分面（refund/coupon 同表两用）、payload 快照原样回读（duplicate 回放的本体）。"""
    async with db_session_factory() as s:
        async with s.begin():
            s.add(
                MockWriteOpRecord(
                    idempotency_key="wo-rt-1",
                    kind="refund",
                    tenant_id="t-mock-rt",
                    payload={"order_id": "mo-rt-1", "amount": "199.99", "result": "ok"},
                )
            )
    async with db_session_factory() as s:
        row = (
            await s.execute(select(MockWriteOpRecord).where(MockWriteOpRecord.idempotency_key == "wo-rt-1"))
        ).scalar_one()
    assert row.kind == "refund"
    assert row.payload == {"order_id": "mo-rt-1", "amount": "199.99", "result": "ok"}
    assert row.created_at is not None


async def test_write_op_idempotency_key_is_primary_key(db_session_factory) -> None:
    """去重的物质基础：同一把幂等键第二次 INSERT 被主键拒绝——交付② ON CONFLICT 算法建立在这条约束上。"""

    def make() -> MockWriteOpRecord:
        return MockWriteOpRecord(idempotency_key="wo-uq-1", kind="refund", tenant_id="t", payload={})

    async with db_session_factory() as s:
        async with s.begin():
            s.add(make())
    with pytest.raises(IntegrityError):
        async with db_session_factory() as s:
            async with s.begin():
                s.add(make())

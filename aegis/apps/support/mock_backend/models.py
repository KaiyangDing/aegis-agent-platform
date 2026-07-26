"""模拟业务系统两表 ORM（M3.7 交付①，plans/m3-detailed §4.7 / D9 拍板）。

D9 只把这两样落 PG（其余 mock 状态留内存，重启即清）：
- mock_orders 是归属校验的事实源（order.tenant_id/user_id × ctx 交叉核验——对抗③），
  也是退款状态流转的载体，必须跨进程稳定；
- mock_write_ops 是 #6 幂等键去重的下游台账：恢复期"凭幂等键安全重发"的语义
  要求去重记录跨崩溃存活——内存字典重启即忘，等于没有去重。
不带 FK（P4 同款口径）；两表都有 tenant_id = RLS 覆盖名单内（P5，迁移自带策略）。
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis.core.db import Base


class MockOrderStatus(StrEnum):
    """mock_orders.status 合法值——String 列 + 代码守护（IngestStatus/RunState 同口径：
    加值改代码，不跑 ALTER TYPE）。"""

    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    REFUNDED = "refunded"  # 退款终态：可退性校验的拒绝依据（已退不能再退）


class MockOrderRecord(Base):
    """mock_orders：演示订单一单一行；归属校验与可退性判断的事实源。"""

    __tablename__ = "mock_orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 演示单号（形如 AZ-20260701-0042）
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)  # RLS 策略列
    user_id: Mapped[str] = mapped_column(String(64), index=True)  # 归属校验列（对抗③：== ctx.user_id）
    status: Mapped[str] = mapped_column(String(16))  # MockOrderStatus.value
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # 钱不过 float（M3.1④ 口径延伸）
    items: Mapped[dict[str, Any]] = mapped_column(JSONB)  # 商品行快照，平台不解释
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MockWriteOpRecord(Base):
    """mock_write_ops：写操作去重台账（#6 闭环的下游端）。

    PK=idempotency_key（值=透传的 tool_call 事件 id——tools.py:40-41 契约）：
    主键冲突即"同一把钥匙第二次开门"，ON CONFLICT DO NOTHING + rowcount 判定
    是去重算法的全部（交付② app.py）；台账跨崩溃存活=恢复期重发安全的物质基础。
    """

    __tablename__ = "mock_write_ops"

    idempotency_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # refund/coupon（同表两用：coupons 复用退款骨架）
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)  # RLS 策略列
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)  # 订单号/金额/结果快照（duplicate 回放的本体）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

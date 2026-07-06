"""计量：usage_ledger 的 ORM 模型（记录器与成本计算在 M1.11b 接入网关）。

设计要点：
- 钱用 Numeric/Decimal，永远不用 float——浮点误差在账本里是事故不是笑话；
- (tenant_id, created_at) 复合索引：租户月度预算闸门与成本视图的主查询路径；
- created_at 用数据库时钟（server_default）：多副本时钟会漂移，账本认一个报时员。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from aegis.core.db import Base


class UsageRecord(Base):
    """usage_ledger：每次 LLM 调用一行——成本治理的原始账本（架构 §3）。"""

    __tablename__ = "usage_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tier: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    completion_tokens: Mapped[int] = mapped_column(Integer)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)  # 缓存回放：记录但零成本
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (Index("ix_usage_tenant_created", "tenant_id", "created_at"),)

"""计量：usage_ledger 的 ORM 模型（记录器与成本计算在 M1.11b 接入网关）。

设计要点：
- 钱用 Numeric/Decimal，永远不用 float——浮点误差在账本里是事故不是笑话；
- (tenant_id, created_at) 复合索引：租户月度预算闸门与成本视图的主查询路径；
- created_at 用数据库时钟（server_default）：多副本时钟会漂移，账本认一个报时员。
"""

import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from aegis.core.db import Base
from aegis.gateway.schema import LLMRequest, UsageChunk

logger = logging.getLogger(__name__)


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


PriceTable = dict[str, tuple[Decimal, Decimal]]  # model → (输入价, 输出价)，元/千 token


def compute_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    *,
    cached: bool,
    prices: PriceTable,
) -> Decimal:
    """一次调用的成本。纯函数：好测，且把'钱怎么算'钉死在一处。"""
    if cached:
        return Decimal("0")  # 缓存回放不打上游，一分钱不花——M1.10 盖的章在此兑现
    pair = prices.get(model)
    if pair is None:
        # 新模型忘补价目表：计费不崩溃，但必须在日志里喊——静默记零是财务事故
        logger.warning("模型 %s 不在价目表中，本行成本记 0（请尽快补配置）", model)
        return Decimal("0")
    prompt_price, completion_price = pair
    return (
        Decimal(prompt_tokens) * prompt_price + Decimal(completion_tokens) * completion_price
    ) / Decimal(1000)


class MeteringRecorder:
    """记账员：把一次调用写成 usage_ledger 的一行；并为预算闸门提供月度聚合读路径。

    自己开会话、自己提交——记账是独立的工作单元，不搭请求主链路的事务。
    记账失败由调用方兜住（绝不拖垮请求），缺口由 M1.12 对账脚本暴露。
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], prices: PriceTable):
        self._sf = session_factory
        self._prices = prices

    async def record(self, req: LLMRequest, provider: str, usage: UsageChunk) -> None:
        cost = compute_cost(
            usage.model,
            usage.prompt_tokens,
            usage.completion_tokens,
            cached=usage.cached,
            prices=self._prices,
        )
        async with self._sf() as session:
            async with session.begin():  # begin 上下文：正常退出即 commit，异常即 rollback
                session.add(
                    UsageRecord(
                        request_id=req.request_id,
                        tenant_id=req.tenant_id,
                        session_id=req.session_id,
                        tier=req.tier,
                        provider=provider,
                        model=usage.model,
                        prompt_tokens=usage.prompt_tokens,
                        completion_tokens=usage.completion_tokens,
                        cached=usage.cached,
                        cost=cost,
                    )
                )

    async def month_spend(self, tenant_id: str) -> int:
        """该租户本月真实消耗的 token 总量（缓存回放不计——预算管的是花钱）。

        月初由数据库端 date_trunc 计算：账本认谁的钟，预算就认谁的钟。
        查询走 (tenant_id, created_at) 复合索引——M1.11a 修那条路就是为了今天。
        """
        stmt = select(
            func.coalesce(func.sum(UsageRecord.prompt_tokens + UsageRecord.completion_tokens), 0)
        ).where(
            UsageRecord.tenant_id == tenant_id,
            UsageRecord.created_at >= func.date_trunc("month", func.now()),
            UsageRecord.cached.is_(False),
        )
        async with self._sf() as session:
            return int((await session.execute(stmt)).scalar_one())

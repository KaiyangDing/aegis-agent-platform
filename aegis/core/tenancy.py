"""租户目录与业务底座两表（M3.1 交付①，plans/m3-detailed §4.1 / D1）。

tenants/users 落 core 而非 apps：认证（api）、预算闸门（gateway）、装配（apps）
三层都要读租户，分层契约 apps→…→core 下三者共同可达的层只有 core（D1 唯一解）。
TenantDirectory 是只读目录：写路径只有种子脚本（#21 治理口径：种子即初始化入口，
运行期只读）；带 TTL 进程缓存（#22 拍板：短缓存，不上 Redis 计数器）。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, String, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from aegis.core.db import Base

SessionFactory = Callable[[], AsyncSession]
"""按形状声明（与 runtime/store.py 同名同形状的本层副本）：core 不得向上 import
runtime 的别名——结构化类型只认形状，重复声明是分层契约下的正确代价。"""


class Role(StrEnum):
    """users.role 合法值（02 §7.1 三档）。存 String 列 + 代码层守护，不用 PG ENUM
    （与 RunState/ApprovalStatus 同口径：加值改代码，不跑 ALTER TYPE）。"""

    USER = "user"
    OPERATOR = "operator"
    ADMIN = "admin"


class TenantRecord(Base):
    """租户：config 对平台不透明（解释权在 L3——spec.py tenant_config 同哲学）；
    token_budget_monthly 独立列不进 config（00 M3.1 行：预算是平台闸门要读的
    结构化数据，不许埋进业务自由域）。"""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 形如 tenant-a（schema.py:54 字符集）
    name: Mapped[str] = mapped_column(String(128))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    token_budget_monthly: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserRecord(Base):
    """用户：role 三档见 Role；不带 FK 指向 tenants（P4 拍板——与既有六表零 FK
    同哲学，隔离靠 WHERE+RLS 不靠参照完整性）。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TenantDirectory:
    """只读目录：认证/预算/装配三消费方共用；命中缓存 TTL 内不回库（#22）。

    只缓存命中（查到行才入缓存）：未知 id 的 miss 每次回库——负缓存会让新种子的
    租户/用户在 TTL 窗内被 401/403 误伤，得不偿失。clock 可注入：缓存过期测试
    不做真实计时（00 §2.2 时序纪律）。
    """

    def __init__(
        self,
        factory: SessionFactory,
        *,
        cache_ttl_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._factory = factory
        self._ttl = cache_ttl_s
        self._clock = clock
        self._tenants: dict[str, tuple[float, TenantRecord]] = {}  # id -> (过期时刻, 行)
        self._users: dict[str, tuple[float, UserRecord]] = {}

    async def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        cached = self._tenants.get(tenant_id)
        if cached is not None and self._clock() < cached[0]:
            return cached[1]
        async with self._factory() as s:
            row = (await s.execute(select(TenantRecord).where(TenantRecord.id == tenant_id))).scalar_one_or_none()
        if row is not None:
            self._tenants[tenant_id] = (self._clock() + self._ttl, row)
        return row

    async def get_user(self, user_id: str) -> UserRecord | None:
        cached = self._users.get(user_id)
        if cached is not None and self._clock() < cached[0]:
            return cached[1]
        async with self._factory() as s:
            row = (await s.execute(select(UserRecord).where(UserRecord.id == user_id))).scalar_one_or_none()
        if row is not None:
            self._users[user_id] = (self._clock() + self._ttl, row)
        return row

    async def monthly_budget(self, tenant_id: str) -> int:
        """未知租户返回 0（=闸门关闭）——与 Settings.tenant_monthly_token_budget
        默认 0 同语义：交付③切 resolver 时行为面不变（P3 不变量）。"""
        tenant = await self.get_tenant(tenant_id)
        return 0 if tenant is None else tenant.token_budget_monthly

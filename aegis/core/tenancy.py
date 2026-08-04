"""租户目录与业务底座两表（M3.1 交付①，plans/m3-detailed §4.1 / D1）。

tenants/users 落 core 而非 apps：认证（api）、预算闸门（gateway）、装配（apps）
三层都要读租户，分层契约 apps→…→core 下三者共同可达的层只有 core（D1 唯一解）。
TenantDirectory 是只读目录：写路径只有种子脚本（#21 治理口径：种子即初始化入口，
运行期只读）；带 TTL 进程缓存（#22 拍板：短缓存，不上 Redis 计数器）。
"""

from __future__ import annotations

import copy
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
from aegis.core.tenant_ctx import current_tenant_id

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


def _copy_tenant(row: TenantRecord) -> TenantRecord:
    """脱缓存副本（M4.7 ②）：缓存里的 detached 实例被认证/预算/装配三消费方共享，
    谁就地改 config（可变 JSONB dict）谁就污染全进程 60s；config 走 deepcopy——
    内层还有 tools 列表，一层浅拷挡不住 append 污染。副本是 transient 对象，
    绝不 session.add（目录是只读面，#21）。"""
    return TenantRecord(
        id=row.id,
        name=row.name,
        config=copy.deepcopy(row.config),
        token_budget_monthly=row.token_budget_monthly,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _copy_user(row: UserRecord) -> UserRecord:
    """同上（M4.7 ②）：users 行无可变容器列，逐字段构造即隔离。"""
    return UserRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        role=row.role,
        display_name=row.display_name,
        created_at=row.created_at,
    )


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
        # M4.7 ①：键含环境身份维度——RLS 让"能读到什么"取决于身份，缓存命中即跳过
        # 回库=跳过 RLS 复核；键不含身份，身份 A 灌进的行会服务身份 B 的命中（users
        # 面当前不可达，一旦为"即时降权"接上 get_user 立刻是越权面）。键含身份后，
        # 每个身份只命中自己灌的行，miss 回库时 RLS 仍在场——缓存是"RLS 结论的
        # 备忘录"而非旁路。owner/无身份态键为 ""（维护面自成一格，不与租户混流）。
        self._tenants: dict[tuple[str, str], tuple[float, TenantRecord]] = {}  # (身份, id) -> (过期时刻, 行)
        self._users: dict[tuple[str, str], tuple[float, UserRecord]] = {}

    @staticmethod
    def _identity() -> str:
        return current_tenant_id.get() or ""

    async def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        key = (self._identity(), tenant_id)
        cached = self._tenants.get(key)
        if cached is not None and self._clock() < cached[0]:
            return _copy_tenant(cached[1])
        async with self._factory() as s:
            row = (await s.execute(select(TenantRecord).where(TenantRecord.id == tenant_id))).scalar_one_or_none()
        if row is None:
            return None
        self._tenants[key] = (self._clock() + self._ttl, row)
        return _copy_tenant(row)

    async def get_user(self, user_id: str) -> UserRecord | None:
        key = (self._identity(), user_id)
        cached = self._users.get(key)
        if cached is not None and self._clock() < cached[0]:
            return _copy_user(cached[1])
        async with self._factory() as s:
            row = (await s.execute(select(UserRecord).where(UserRecord.id == user_id))).scalar_one_or_none()
        if row is None:
            return None
        self._users[key] = (self._clock() + self._ttl, row)
        return _copy_user(row)

    async def monthly_budget(self, tenant_id: str) -> int:
        """未知租户返回 0（=闸门关闭）——与 Settings.tenant_monthly_token_budget
        默认 0 同语义：交付③切 resolver 时行为面不变（P3 不变量）。"""
        tenant = await self.get_tenant(tenant_id)
        return 0 if tenant is None else tenant.token_budget_monthly

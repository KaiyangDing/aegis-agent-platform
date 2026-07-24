"""数据库层：应用引擎（低权 aegis_app + 租户钩子）与维护面 owner 引擎（M3.3 起双轨）。

资源 → 手动 global 懒单例（同族第三例）。双轨即 D3/D4：
- get_engine()/get_session_factory()：应用运行时——aegis_app 角色（无 BYPASSRLS，
  RLS 兜底防线真实存在）+ install_tenant_guard（每事务注入租户上下文）；
- get_owner_engine()/get_owner_session_factory()：维护面（reaper 跨租户扫描/种子/
  凭证发放/对账）与 alembic——owner 直连，不挂钩子、不冒充任何租户（D4）。
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from aegis.core.config import get_settings
from aegis.core.tenant_ctx import install_tenant_guard


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类——alembic 靠它的 metadata 发现表结构。"""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_owner_engine: AsyncEngine | None = None
_owner_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """应用引擎：M3.3 起连 aegis_app（database_url_app）并挂租户钩子。"""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url_app,
            pool_size=5,  # 三处连接池的最后一处（架构 §6）：常驻连接数
            max_overflow=10,  # 高峰可临时再借的连接数
            pool_pre_ping=True,  # 借出前探活，挡住数据库重启后的"半死连接"
        )
        install_tenant_guard(_engine)  # 每事务 BEGIN 后注入租户（未设=空串 → RLS 空集）
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        # expire_on_commit=False：commit 后对象属性仍可读（async 下访问过期属性会隐式 IO，禁）
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


def get_owner_engine() -> AsyncEngine:
    """维护面引擎：owner 直连、无租户钩子（D4——平台特权路径，不冒充任何租户）。"""
    global _owner_engine
    if _owner_engine is None:
        _owner_engine = create_async_engine(
            get_settings().database_url,
            pool_size=2,  # 维护面低并发（beat 任务/脚本），不与业务抢连接
            max_overflow=3,
            pool_pre_ping=True,
        )
    return _owner_engine


def get_owner_session_factory() -> async_sessionmaker[AsyncSession]:
    global _owner_session_factory
    if _owner_session_factory is None:
        _owner_session_factory = async_sessionmaker(get_owner_engine(), expire_on_commit=False)
    return _owner_session_factory

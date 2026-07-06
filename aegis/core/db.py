"""数据库层：SQLAlchemy async 引擎与会话工厂（资源 → 手动 global 懒单例，同族第三例）。"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from aegis.core.config import get_settings


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类——alembic 靠它的 metadata 发现表结构。"""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url,
            pool_size=5,  # 三处连接池的最后一处（架构 §6）：常驻连接数
            max_overflow=10,  # 高峰可临时再借的连接数
            pool_pre_ping=True,  # 借出前探活，挡住数据库重启后的"半死连接"
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        # expire_on_commit=False：commit 后对象属性仍可读（async 下访问过期属性会隐式 IO，禁）
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory

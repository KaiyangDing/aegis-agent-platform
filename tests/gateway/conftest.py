"""gateway 测试共享夹具：conftest.py 里的夹具被同目录所有测试自动发现，无需 import。"""

import os

import pytest
import redis.asyncio as aioredis

TEST_REDIS_URL = os.environ.get("AEGIS_TEST_REDIS_URL", "redis://localhost:6379/9")


@pytest.fixture
async def r():
    client = aioredis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:
        if os.environ.get("CI"):
            raise  # CI 里 Redis 必须在——静默跳过等于守卫失效
        pytest.skip("本地 Redis 未启动：docker compose -f deploy/docker-compose.yml up -d")
    # db9 是专用测试库：开跑前清空，防止跨分支/跨 worktree 的确定性 key 读到旧值
    await client.flushdb()
    yield client
    await client.aclose()


TEST_DATABASE_URL = os.environ.get(
    "AEGIS_TEST_DATABASE_URL", "postgresql+asyncpg://aegis:aegis@localhost:5432/aegis"
)


@pytest.fixture
async def db_session():
    """事务回滚式 DB 夹具：测试里的一切写入在结束时整体回滚——不脏库、无需清理。

    这是 SQLAlchemy 测试的标准姿势：连接上手动开事务、会话绑在这条连接上，
    测试结束 rollback——比"测完删数据"可靠（断言失败也不留残渣）。
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from aegis.core.db import Base

    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)  # 本地兜底；正式演进走 alembic
    except Exception:
        await engine.dispose()
        if os.environ.get("CI"):
            raise
        pytest.skip("本地 PostgreSQL 未启动：docker compose -f deploy/docker-compose.yml up -d")
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()  # 整个测试的写入一笔勾销
    await engine.dispose()

"""gateway 测试共享夹具：conftest.py 里的夹具被同目录所有测试自动发现，无需 import。"""

import os

import pytest
import redis.asyncio as aioredis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

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


@pytest.fixture
async def dead_r():
    """指向无人监听端口的客户端：模拟 Redis 整体不可用（超时与重试调到最小——
    redis-py 8 默认 retries=10 + 指数退避，一次失败调用要白睡约 2 秒）。"""
    client = aioredis.from_url(
        "redis://localhost:6399/0",
        socket_connect_timeout=0.1,
        socket_timeout=0.1,
        retry=Retry(NoBackoff(), 0),  # 失败一次出结果，不进默认退避
        decode_responses=True,
    )
    yield client
    await client.aclose()


TEST_DATABASE_URL = os.environ.get("AEGIS_TEST_DATABASE_URL", "postgresql+asyncpg://aegis:aegis@localhost:5432/aegis")


@pytest.fixture
async def db_conn():
    """一条带外层事务的连接：测试里发生的一切在结束时整体回滚。"""
    from sqlalchemy.ext.asyncio import create_async_engine

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
        yield conn
        await trans.rollback()  # 一笔勾销
    await engine.dispose()


@pytest.fixture
def db_session_factory(db_conn):
    """绑在测试连接上的会话工厂：给'自己开会话自己 commit'的组件（如记账员）注入。

    join_transaction_mode="create_savepoint"：这些会话的 commit 只提交 SAVEPOINT
    （事务内的书签），外层 rollback 照样把一切吞掉——被测组件真实提交，测试库零污染。
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(bind=db_conn, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest.fixture
async def db_session(db_session_factory):
    async with db_session_factory() as session:
        yield session

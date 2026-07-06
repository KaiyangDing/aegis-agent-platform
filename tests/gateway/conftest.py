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

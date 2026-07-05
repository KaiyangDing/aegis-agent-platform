"""Redis 异步客户端的进程级懒单例（模式与 gateway/providers/base.shared_client 同款）。"""

import redis.asyncio as aioredis

from aegis.core.config import get_settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            get_settings().redis_url,
            decode_responses=True,  # 返回 str 而非 bytes——本项目存的都是文本
        )
    return _client

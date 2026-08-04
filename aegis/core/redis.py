"""Redis 异步客户端的进程级懒单例（模式与 gateway/providers/base.shared_client 同款）。"""

import redis.asyncio as aioredis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from aegis.core.config import get_settings
from aegis.core.loopcheck import LoopBoundGuard

_client: aioredis.Redis | None = None
_guard = LoopBoundGuard(
    "get_redis() 的 Redis 客户端",
    hint="worker/脚本的新 loop 世界请用 new_redis_client() 现建现用（M3.9④ 受控缝）。",
    strict=False,  # ㉝：既有装置面广，先响亮警告观察一个里程碑（偏差登记）
)


def new_redis_client() -> aioredis.Redis:
    """按仓库口径新建客户端——单例与任务局部实例的唯一配置源（M3.9④）。

    worker 每任务 asyncio.run 新建 event loop，get_redis() 单例绑创建时的 loop
    不可复用——任务体用本函数现建、finally aclose（超时/重试口径只此一处不漂移）。
    """
    return aioredis.from_url(
        get_settings().redis_url,
        decode_responses=True,  # 返回 str 而非 bytes——本项目存的都是文本
        # 快速失败三件：Redis 在本架构里是"可降级依赖"（限流/熔断/缓存/计量
        # 各自带降级），检测要快、绝不拖垮请求。redis-py 8 默认 retries=10 +
        # 指数抖动退避，一次失败调用拖 ~3s，与自带降级是重复兜底——砍成
        # 零退避重试 1 次（只为吃掉"池里连接已死、重连即好"的常见毛刺）。
        socket_connect_timeout=1.0,
        socket_timeout=2.0,
        retry=Retry(NoBackoff(), 1),
    )


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = new_redis_client()
    _guard.check(_client)  # M4.7 ㉝：跨 loop 复用给人话预警，不等深处裸炸
    return _client

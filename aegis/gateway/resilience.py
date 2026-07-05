"""受控重试：只在安全窗口内、只对可恢复的错误、在预算内重试。

三条铁律：
1. 只重试无业务副作用的操作——LLM 补全可重复执行，唯一代价是重复计费，
   所以尝试次数与总时限都有硬预算；
2. 只在"首块之前"重试——一旦有 chunk 流向下游，重试会造成重复输出；
   中途失败属于"半截输出"问题，归上层（L2 恢复语义）处置；
3. 退避 = 指数 + 满抖动，429 优先服从服务端 Retry-After——
   无抖动的同步重试会让所有客户端一起冲撞刚恢复的上游（惊群）。
"""

import asyncio
import random
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from aegis.gateway.errors import (
    ProviderServerError,
    ProviderTimeoutError,
    RateLimitedError,
)
from aegis.gateway.providers.base import Provider
from aegis.gateway.schema import LLMChunk, LLMRequest

RETRYABLE_ERRORS = (RateLimitedError, ProviderTimeoutError, ProviderServerError)

# 测试接缝：单测替换这两个名字来记录/加速，而不是打全局 asyncio/random 的补丁
_sleep = asyncio.sleep
_uniform = random.uniform


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3  # 总尝试次数（含第一次）
    base_backoff: float = 0.5  # 首次退避基数（秒）
    max_backoff: float = 8.0  # 单次退避上限
    total_timeout: float = 60.0  # 重试总预算：超时放弃，别让用户干等


def compute_backoff(attempt: int, policy: RetryPolicy, retry_after: float | None) -> float:
    """服务端指令优先；否则指数增长 + 满抖动。"""
    if retry_after is not None:
        return min(retry_after, policy.max_backoff)
    cap = min(policy.base_backoff * (2 ** (attempt - 1)), policy.max_backoff)
    return _uniform(0.0, cap)


async def complete_with_retry(
    provider: Provider,
    req: LLMRequest,
    model: str,
    policy: RetryPolicy | None = None,
) -> AsyncIterator[LLMChunk]:
    policy = policy or RetryPolicy()
    start = time.monotonic()  # 单调钟：测时长不用壁钟（壁钟会被校时跳变）
    attempt = 0
    while True:
        attempt += 1
        stream = provider.complete(req, model)
        try:
            first = await anext(stream)
        except StopAsyncIteration:
            return  # 空流：协议不变量下不该发生，防御性处理
        except RETRYABLE_ERRORS as e:
            if attempt >= policy.max_attempts:
                raise
            delay = compute_backoff(attempt, policy, getattr(e, "retry_after", None))
            if time.monotonic() - start + delay > policy.total_timeout:
                raise
            await _sleep(delay)
            continue
        # 首块已到手：从此进入"不可重试区"，任何错误原样上抛
        yield first
        async for chunk in stream:
            yield chunk
        return

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
from collections.abc import AsyncGenerator
from contextlib import aclosing
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
    total_timeout: float = 60.0  # 单候选重试总预算：超时放弃，别让用户干等
    # —— §2.2 超时语义（评审 C1）——
    first_chunk_timeout: float = 25.0  # 首块超时：切断"连上了但不吐字"的挂起形态
    min_attempt_budget: float = 8.0  # deadline 剩余低于此值不再开新尝试（连接+快速首块的下限）


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
    *,
    deadline: float | None = None,  # 绝对单调钟时刻：req.deadline_s 由 router 换算而来
) -> AsyncGenerator[LLMChunk]:
    policy = policy or RetryPolicy()
    start = time.monotonic()  # 单调钟：测时长不用壁钟（壁钟会被校时跳变）
    attempt = 0
    while True:
        attempt += 1
        stream = provider.complete(req, model)
        try:
            # 首块窗口上双闸：参数闸（first_chunk_timeout）与全局闸（deadline 剩余）取小。
            # 首块前无任何输出流向下游，asyncio.timeout 取消 anext 是安全的
            first_wait = policy.first_chunk_timeout
            if deadline is not None:
                first_wait = min(first_wait, max(0.0, deadline - time.monotonic()))
            try:
                async with asyncio.timeout(first_wait):
                    first = await anext(stream)
            except TimeoutError as e:
                # 挂起统一翻译成 ProviderTimeoutError：与 5xx 走同一条
                # 重试/记熔断账/换路流水线——评审 C1 要求的"挂起可被处理"就在这一行
                await stream.aclose()  # 显式归还悬挂中的 httpx 连接，不等 GC
                raise ProviderTimeoutError(provider.name, f"首块超时 >{first_wait:.1f}s（上游挂起）") from e
        except StopAsyncIteration:
            return  # 空流：协议不变量下不该发生，防御性处理
        except RETRYABLE_ERRORS as e:
            if attempt >= policy.max_attempts:
                raise
            delay = compute_backoff(attempt, policy, getattr(e, "retry_after", None))
            now = time.monotonic()
            if now - start + delay > policy.total_timeout:
                raise
            if deadline is not None and now + delay + policy.min_attempt_budget > deadline:
                raise  # 全局首块预算不够再开一次像样的尝试：真实死因原样上抛，不造新异常
            # ↑ 注意这两个 raise 裸抛的都是 e——预算耗尽不是新故障，死因是真实的上游错误
            await _sleep(delay)
            continue
        # 首块已到手：从此进入"不可重试区"，任何错误原样上抛。
        # aclosing：消费者提前挂断时 GeneratorExit 同步传进 provider 生成器，
        # httpx 流式连接立刻归还池子，不等 GC 终结器（审计加固 C）
        async with aclosing(stream) as inner:
            yield first
            async for chunk in inner:
                yield chunk
        return

"""压测口径① 的固定延迟上游（M5.2 D1；00 §9.1 M5.2——参数是口径不许改，§3.1）。

首 token 800ms + 20 tok/s：与 C1 超时语义刻意耦合——块间隔 50ms ≪ 空闲超时 30s、
首 token 0.8s ≪ 首块超时 25s，"长回答是健康的"这句面试解释依赖这组数。
挂 Provider 层（与 FaultInjector 同层同法）让**整个平台栈为真**：限流/熔断/缓存/
计量/运行时/SSE 全在被测路径上，只有上游是假的——这正是"平台自身开销"的测量面。
不变量：不抛业务异常、不读网络——它是"永远健康的上游"，自身耗时只有注入的延迟。
sleep 可注入：时序不进 CI（00 §2.2），测试用记录桩替真睡（ToolExecutor 先例）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable

from aegis.core.tokens import estimate_tokens
from aegis.gateway.schema import LLMChunk, LLMRequest, StopChunk, TextDelta, UsageChunk


class LatencyModelProvider:
    """永远健康的固定延迟上游（Provider 协议形状：name + complete(req, model)）。"""

    def __init__(
        self,
        name: str = "latency-model",
        *,
        first_token_s: float = 0.8,
        tokens_per_s: float = 20.0,
        response_tokens: int = 200,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.name = name
        self._first_token_s = first_token_s
        self._tokens_per_s = tokens_per_s
        self._response_tokens = response_tokens
        self._sleep = sleep

    async def complete(self, req: LLMRequest, model: str) -> AsyncGenerator[LLMChunk]:
        await self._sleep(self._first_token_s)
        for _ in range(self._response_tokens):
            yield TextDelta(text="测")
            await self._sleep(1.0 / self._tokens_per_s)
        prompt_est = estimate_tokens("".join(m.content or "" for m in req.messages))
        yield UsageChunk(model=model, prompt_tokens=prompt_est, completion_tokens=self._response_tokens)
        yield StopChunk(reason="end_turn")

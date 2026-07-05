"""档位路由 + fallback 矩阵：网关的总装车间。

装配顺序（每个请求）：
  租户配额（环外一次）→ 沿候选链：熔断闸门 → 供应商限流 → [故障注入] → 受控重试 → 适配器

两条安全红线：
- 半截不换路：有 chunk 流出后任何失败原样上抛（重试层"首块窗口"在路由层的镜像）；
- 租户配额在候选环外：换供应商换不掉租户身份，配额尽则立刻明确失败。

异常三待遇：5xx/超时记熔断账再换路；429 换路不记账（上游活着）；
Auth/BadRequest 换路不记账（本家配置/转换问题，如历史转 Anthropic 失败）。
"""

import random
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from aegis.gateway.errors import (
    AuthError,
    BadRequestError,
    GatewayExhausted,
    ProviderServerError,
    ProviderTimeoutError,
    RateLimitedError,
)
from aegis.gateway.providers.base import Provider
from aegis.gateway.resilience import RetryPolicy, complete_with_retry
from aegis.gateway.schema import LLMChunk, LLMRequest, UsageChunk

_PROBE_POLICY = RetryPolicy(max_attempts=1)  # 探针一次定胜负，别拿重试预算拖长半开期
_BREAKER_COUNTED = (ProviderServerError, ProviderTimeoutError)

_random = random.random  # 测试接缝


class BreakerLike(Protocol):
    async def allow(self, provider: str) -> str: ...
    async def on_success(self, provider: str) -> None: ...
    async def on_failure(self, provider: str) -> None: ...


class LimiterLike(Protocol):
    async def wait_take(
        self, scope: str, rate: float, capacity: float, *, max_wait: float = 10.0, cost: float = 1.0
    ) -> bool: ...


class CacheLike(Protocol):
    async def get(self, req: LLMRequest) -> list[LLMChunk] | None: ...
    async def put(self, req: LLMRequest, chunks: list[LLMChunk]) -> None: ...


@dataclass(frozen=True)
class Candidate:
    provider: str
    model: str


def parse_routes(
    raw: dict[str, list[str]], known_providers: set[str]
) -> dict[str, list[Candidate]]:
    """启动即校验：路由配置错误要在进程启动时炸，不许拖到运行时。"""
    routes: dict[str, list[Candidate]] = {}
    for tier, entries in raw.items():
        cands: list[Candidate] = []
        for entry in entries:
            provider, sep, model = entry.partition(":")
            if not sep or not model or provider not in known_providers:
                raise ValueError(f"路由配置非法: {tier} -> {entry!r}")
            cands.append(Candidate(provider, model))
        routes[tier] = cands
    return routes


@dataclass(frozen=True)
class GatewayLimits:
    provider_rate: float = 8.0
    provider_burst: float = 16.0
    tenant_rate: float = 5.0
    tenant_burst: float = 10.0
    max_wait: float = 10.0


class FaultInjector:
    """Provider 的装饰器：按概率在首块前抛 5xx——演示/实验专用。

    自己就实现 Provider 协议，重试/熔断对它一视同仁，不知道故障是演的。
    只在首块前注入（模拟连接阶段失败），保证可被重试/熔断/换路完整处理。
    """

    def __init__(self, inner: Provider, rate: float):
        self._inner = inner
        self._rate = rate
        self.name = inner.name

    async def complete(self, req: LLMRequest, model: str) -> AsyncIterator[LLMChunk]:
        if _random() < self._rate:
            raise ProviderServerError(self.name, "故障注入（fault_injection_rate）")
        async for chunk in self._inner.complete(req, model):
            yield chunk


class LLMGateway:
    def __init__(
        self,
        *,
        providers: dict[str, Provider],
        routes: dict[str, list[Candidate]],
        breaker: BreakerLike,
        limiter: LimiterLike,
        cache: CacheLike | None = None,
        limits: GatewayLimits | None = None,
        retry_policy: RetryPolicy | None = None,
        fault_rate: float = 0.0,
        fault_targets: frozenset[str] = frozenset(),
    ):
        self._providers = providers
        self._routes = routes
        self._breaker = breaker
        self._limiter = limiter
        self._cache = cache
        self._limits = limits or GatewayLimits()
        self._retry_policy = retry_policy or RetryPolicy()
        self._fault_rate = fault_rate
        self._fault_targets = fault_targets

    async def complete(self, req: LLMRequest) -> AsyncIterator[LLMChunk]:
        # 最外圈：缓存命中 = 零上游成本，不该消耗任何配额、不该问任何闸门
        if self._cache is not None:
            hit = await self._cache.get(req)
            if hit is not None:
                for chunk in hit:
                    if isinstance(chunk, UsageChunk):
                        chunk = chunk.model_copy(update={"cached": True})  # 盖缓存章
                    yield chunk
                return

        # 红线二：租户配额在候选环外——换供应商换不掉租户身份
        ok = await self._limiter.wait_take(
            f"tenant:{req.tenant_id}",
            self._limits.tenant_rate,
            self._limits.tenant_burst,
            max_wait=self._limits.max_wait,
        )
        if not ok:
            raise RateLimitedError("tenant-quota", f"租户 {req.tenant_id} 出站配额耗尽")

        last_error: Exception | None = None
        for cand in self._routes[req.tier]:
            provider = self._providers[cand.provider]

            decision = await self._breaker.allow(cand.provider)
            if decision == "deny":
                continue

            ok = await self._limiter.wait_take(
                f"provider:{cand.provider}",
                self._limits.provider_rate,
                self._limits.provider_burst,
                max_wait=self._limits.max_wait,
            )
            if not ok:
                continue  # 这家连排队都排不上，换下一站

            target: Provider = provider
            if self._fault_rate > 0 and f"{cand.provider}:{cand.model}" in self._fault_targets:
                target = FaultInjector(provider, self._fault_rate)

            policy = _PROBE_POLICY if decision == "probe" else self._retry_policy
            yielded = False
            buffer: list[LLMChunk] = []
            try:
                async for chunk in complete_with_retry(target, req, cand.model, policy):
                    yielded = True
                    if self._cache is not None:
                        buffer.append(chunk)
                    yield chunk
                await self._breaker.on_success(cand.provider)
                if self._cache is not None:
                    await self._cache.put(req, buffer)  # 只有完整走完才会执行到这
                return
            except _BREAKER_COUNTED as e:
                await self._breaker.on_failure(cand.provider)
                if yielded:
                    raise  # 红线一：半截不换路
                last_error = e
            except RateLimitedError as e:
                if yielded:
                    raise
                last_error = e  # 429 不记熔断账：上游活着，只是挤
            except (AuthError, BadRequestError) as e:
                if yielded:
                    raise
                last_error = e  # 本家的配置/转换问题，别家未必过不去

        raise GatewayExhausted(f"档位 {req.tier} 的所有候选均不可用") from last_error

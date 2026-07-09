"""档位路由 + fallback 矩阵：网关的总装车间。

装配顺序（每个请求）：
  租户配额（环外一次）→ 沿候选链：熔断闸门 → 供应商限流 → [故障注入] → 受控重试 → 适配器

两条安全红线：
- 半截不换路：有 chunk 流出后任何失败原样上抛（重试层"首块窗口"在路由层的镜像）；
- 租户配额在候选环外：换供应商换不掉租户身份，配额尽则立刻明确失败。

异常三待遇：5xx/超时记熔断账再换路；429 换路不记账（上游活着）；
Auth/BadRequest 换路不记账（本家配置/转换问题，如历史转 Anthropic 失败）。
"""

import asyncio
import json
import logging
import random
import time
from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import dataclass
from typing import Literal, Protocol, get_args

from aegis.core.tokens import estimate_tokens
from aegis.gateway.errors import (
    AuthError,
    BadRequestError,
    BudgetExceeded,
    GatewayExhausted,
    GatewayRejected,
    GatewayStreamInterrupted,
    ProviderServerError,
    ProviderTimeoutError,
    RateLimitedError,
    TenantQuotaExceeded,
)
from aegis.gateway.providers.base import Provider
from aegis.gateway.resilience import RetryPolicy, complete_with_retry
from aegis.gateway.schema import LLMChunk, LLMRequest, Tier, UsageChunk

logger = logging.getLogger(__name__)

_PROBE_POLICY = RetryPolicy(max_attempts=1)  # 探针一次定胜负，别拿重试预算拖长半开期
_BREAKER_COUNTED = (ProviderServerError, ProviderTimeoutError)

_random = random.random  # 测试接缝
_hang_sleep = asyncio.sleep  # 测试接缝：hang 注入的睡眠可替换/可观测
FaultMode = Literal["error", "hang", "midstream"]


class BreakerLike(Protocol):
    async def allow(self, provider: str) -> str: ...

    async def on_success(self, provider: str) -> None: ...

    async def on_failure(self, provider: str) -> None: ...

    async def release_probe(self, provider: str) -> None: ...


class LimiterLike(Protocol):
    async def wait_take(self, scope: str, rate: float, capacity: float, *, max_wait: float = 10.0, cost: float = 1.0) -> bool: ...


class CacheLike(Protocol):
    async def get(self, req: LLMRequest) -> list[LLMChunk] | None: ...

    async def put(self, req: LLMRequest, chunks: list[LLMChunk]) -> None: ...


class MeterLike(Protocol):
    async def record(self, req: LLMRequest, provider: str, usage: UsageChunk) -> None: ...

    async def month_spend(self, tenant_id: str) -> int: ...


@dataclass(frozen=True)
class Candidate:
    provider: str
    model: str


def parse_routes(raw: dict[str, list[str]], known_providers: set[str]) -> dict[str, list[Candidate]]:
    """启动即校验：路由配置错误要在进程启动时炸，不许拖到运行时。"""
    routes: dict[str, list[Candidate]] = {}
    for tier, entries in raw.items():
        cands: list[Candidate] = []
        for entry in entries:
            provider, sep, model = entry.partition(":")
            if not sep or not model or provider not in known_providers:
                raise ValueError(f"路由配置非法: {tier} -> {entry!r}")
            cands.append(Candidate(provider, model))
        if not cands:
            raise ValueError(f"档位 {tier} 的候选链为空")
        routes[tier] = cands
    # 齐档校验：MODEL_ROUTES 被环境变量整体覆盖时最容易漏档——启动即炸，
    # 别让第一个 strong 请求在凌晨三点用 KeyError 告诉你（以 schema.Tier 为单一事实源）
    missing = set(get_args(Tier)) - routes.keys()
    if missing:
        raise ValueError(f"路由配置缺少档位: {sorted(missing)}（fast/standard/strong 必须齐全）")
    return routes


def estimate_request_tokens(req: LLMRequest) -> int:
    """请求入口侧的规模估算：messages 全文 + 工具说明书。
    只估 prompt 侧——输出上界由 max_tokens 参数本身约束，不重复设闸。"""
    total = sum(estimate_tokens(m.content) for m in req.messages)
    for t in req.tools:
        total += estimate_tokens(t.name) + estimate_tokens(t.description)
        total += estimate_tokens(json.dumps(t.parameters, ensure_ascii=False))
    return total


@dataclass(frozen=True)
class GatewayLimits:
    provider_rate: float = 8.0
    provider_burst: float = 16.0
    tenant_rate: float = 5.0
    tenant_burst: float = 10.0
    max_wait: float = 10.0


class FaultInjector:
    """Provider 的装饰器：按概率注入三种故障形态——演示/实验专用。

    自己就实现 Provider 协议，重试/熔断对它一视同仁，不知道故障是演的。
    - error：首块前抛 5xx（M1 原有形态，模拟连接阶段失败）；
    - hang：首块前挂起不吐字（评审 C1 的盲区——由首块超时真实切断，不是模拟切断）；
    - midstream：吐出首块后死掉（触发半截语义 GatewayStreamInterrupted）。
    """

    def __init__(self, inner: Provider, rate: float, *, mode: FaultMode = "error", hang_s: float = 120.0):
        self._inner = inner
        self._rate = rate
        self._mode = mode
        self._hang_s = hang_s
        self.name = inner.name

    async def complete(self, req: LLMRequest, model: str) -> AsyncGenerator[LLMChunk]:
        inject = _random() < self._rate
        if inject and self._mode == "error":
            raise ProviderServerError(self.name, "故障注入（error）")
        if inject and self._mode == "hang":
            await _hang_sleep(self._hang_s)  # 等着被首块超时取消——考验真实机制
            raise ProviderServerError(self.name, "故障注入（hang 兜底，正常不应到达）")
        async with aclosing(self._inner.complete(req, model)) as inner:
            if inject and self._mode == "midstream":
                first = await anext(inner, None)
                if first is not None:
                    yield first  # 首块已流出——下游进入"半截"境地
                raise ProviderTimeoutError(self.name, "故障注入（midstream：首块后断流）")
            async for chunk in inner:
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
        meter: MeterLike | None = None,
        monthly_token_budget: int = 0,
        request_token_budget: int = 0,
        limits: GatewayLimits | None = None,
        retry_policy: RetryPolicy | None = None,
        fault_rate: float = 0.0,
        fault_targets: frozenset[str] = frozenset(),
        fault_mode: FaultMode = "error",
    ):
        self._providers = providers
        self._routes = routes
        self._breaker = breaker
        self._limiter = limiter
        self._cache = cache
        self._meter = meter
        self._monthly_token_budget = monthly_token_budget
        self._request_token_budget = request_token_budget
        self._limits = limits or GatewayLimits()
        self._retry_policy = retry_policy or RetryPolicy()
        self._fault_rate = fault_rate
        self._fault_targets = fault_targets
        self._fault_mode = fault_mode

    async def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        # 配置防御：parse_routes 已保证齐档，但手工构造的路由表（如测试）可能缺档——
        # 在消耗任何配额之前干净地失败
        candidates = self._routes.get(req.tier)
        if not candidates:
            raise GatewayExhausted(f"档位 {req.tier} 没有配置任何候选（检查 MODEL_ROUTES）")

        # §2.2 超时语义（评审 C1）：deadline 只约束"首块前"的空转。换算成绝对单调钟
        # 沿候选链与重试层传播；首块流出后不再看它——整流不设上限，块间空闲由 httpx read 守护
        deadline: float | None = None
        if req.deadline_s is not None:
            deadline = time.monotonic() + req.deadline_s

        # 最外圈：缓存命中 = 零上游成本，不该消耗任何配额、不该问任何闸门。
        # 缓存的任何故障（连接失败/脏数据）都退化为 miss——缓存永远不许拖死主链路
        if self._cache is not None:
            hit: list[LLMChunk] | None = None
            try:
                hit = await self._cache.get(req)
            except Exception:
                logger.warning("缓存读取失败，按 miss 处理", exc_info=True)
            if hit is not None:
                hit_usage: UsageChunk | None = None
                for chunk in hit:
                    if isinstance(chunk, UsageChunk):
                        chunk = chunk.model_copy(update={"cached": True})  # 盖缓存章
                        hit_usage = chunk
                    yield chunk
                if hit_usage is not None:
                    # 命中也记账（provider="cache"，成本 0）——命中率统计的分母在这
                    await self._safe_record(req, "cache", hit_usage)
                return

        # 租户月度预算闸门（软预算 fail-open：账本读挂了放行并告警——
        # 成本护栏不是安全边界，为一次账本抖动拒绝所有用户是代价倒挂）
        if self._meter is not None and self._monthly_token_budget > 0:
            try:
                spent = await self._meter.month_spend(req.tenant_id)
            except Exception:
                logger.warning("预算读取失败，本次放行（fail-open）", exc_info=True)
            else:
                if spent >= self._monthly_token_budget:
                    raise BudgetExceeded(f"租户 {req.tenant_id} 本月已用 {spent} token，预算 {self._monthly_token_budget}")

        # 单请求预算闸门（三级预算的 L1 级，§10.1 #1）：挡超长上下文炸弹。
        # 在租户限流之前——被拒的请求不该消耗配额；估算口径 ±15%（00 §2.2）
        if self._request_token_budget > 0:
            est = estimate_request_tokens(req)
            if est > self._request_token_budget:
                raise BudgetExceeded(f"单请求估算 {est} token，超过预算 {self._request_token_budget}（估算口径 00 §2.2）")

        # 红线二：租户配额在候选环外——换供应商换不掉租户身份
        ok = await self._limiter.wait_take(
            f"tenant:{req.tenant_id}",
            self._limits.tenant_rate,
            self._limits.tenant_burst,
            max_wait=self._limits.max_wait,
        )
        if not ok:
            # 契约内类型（加固 B）：租户配额不是"某供应商限流"，不许冒充 ProviderError
            raise TenantQuotaExceeded(f"租户 {req.tenant_id} 出站配额耗尽")

        last_error: Exception | None = None
        budget_out = False
        rejections = 0  # 确定性拒绝（Auth/BadRequest）计数
        transients = 0  # 暂时性因素计数：熔断拒/限流拒/5xx/超时/429
        for cand in candidates:
            if deadline is not None and deadline - time.monotonic() < self._retry_policy.min_attempt_budget:
                budget_out = True  # 剩余预算连一次像样的尝试都开不起：停止换路
                break
            provider = self._providers[cand.provider]

            decision = await self._breaker.allow(cand.provider)
            if decision == "deny":
                transients += 1
                continue

            ok = await self._limiter.wait_take(
                f"provider:{cand.provider}",
                self._limits.provider_rate,
                self._limits.provider_burst,
                max_wait=self._limits.max_wait,
            )
            if not ok:
                if decision == "probe":
                    # 领了全集群唯一的探测令牌却没打出去——必须归还，否则半开期空转
                    await self._breaker.release_probe(cand.provider)
                transients += 1
                continue  # 这家连排队都排不上，换下一站

            target: Provider = provider
            if self._fault_rate > 0 and f"{cand.provider}:{cand.model}" in self._fault_targets:
                target = FaultInjector(provider, self._fault_rate, mode=self._fault_mode)

            policy = _PROBE_POLICY if decision == "probe" else self._retry_policy
            yielded = False
            buffer: list[LLMChunk] = []
            usage_seen: UsageChunk | None = None
            try:
                async with aclosing(complete_with_retry(target, req, cand.model, policy, deadline=deadline)) as rs:
                    async for chunk in rs:
                        yielded = True
                        if isinstance(chunk, UsageChunk):
                            usage_seen = chunk
                        if self._cache is not None:
                            buffer.append(chunk)
                        yield chunk
                await self._breaker.on_success(cand.provider)
                if self._cache is not None:
                    try:
                        await self._cache.put(req, buffer)
                    except Exception:
                        logger.warning("缓存写入失败，跳过", exc_info=True)
                if usage_seen is not None:
                    await self._safe_record(req, cand.provider, usage_seen)
                return
            except _BREAKER_COUNTED as e:
                await self._breaker.on_failure(cand.provider)
                if yielded:
                    # 红线一：半截不换路。包装成契约内的流中断类型（加固 B）——
                    # ProviderError 家族不穿出网关，原始死因在 __cause__
                    raise GatewayStreamInterrupted(f"流中断于 {cand.provider}:{cand.model}") from e
                transients += 1
                last_error = e
            except RateLimitedError as e:
                if decision == "probe":
                    # 429 不构成熔断裁决——令牌归还，别让半开期干等 probe_ttl
                    await self._breaker.release_probe(cand.provider)
                if yielded:
                    raise GatewayStreamInterrupted(f"流中断于 {cand.provider}:{cand.model}") from e
                transients += 1
                last_error = e  # 429 不记熔断账：上游活着，只是挤
            except (AuthError, BadRequestError) as e:
                if decision == "probe":
                    await self._breaker.release_probe(cand.provider)
                if yielded:
                    raise GatewayStreamInterrupted(f"流中断于 {cand.provider}:{cand.model}") from e
                rejections += 1
                last_error = e  # 本家的配置/转换问题，别家未必过不去

        if budget_out:
            raise GatewayExhausted(f"档位 {req.tier} 首块预算 {req.deadline_s}s 耗尽（候选链未走完）") from last_error

        if rejections > 0 and transients == 0:
            raise GatewayRejected(f"档位 {req.tier} 全部候选均被确定性拒绝——检查 API key 配置与请求转换") from last_error

        raise GatewayExhausted(f"档位 {req.tier} 的所有候选均不可用") from last_error

    async def _safe_record(self, req: LLMRequest, provider: str, usage: UsageChunk) -> None:
        """记账失败绝不拖垮请求——为了发票烧掉货物是荒唐的；缺口留给对账脚本暴露。"""
        if self._meter is None:
            return
        try:
            await self._meter.record(req, provider, usage)
        except Exception:
            logger.warning("计量写入失败（对账脚本会暴露此缺口）", exc_info=True)

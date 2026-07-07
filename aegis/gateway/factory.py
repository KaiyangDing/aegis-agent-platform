"""组装在边缘：真实依赖只在这里聚合成完整网关，其余代码一律靠注入。"""

from decimal import Decimal

from aegis.core.config import get_settings
from aegis.core.db import get_session_factory
from aegis.core.redis import get_redis
from aegis.gateway.breaker import CircuitBreaker
from aegis.gateway.cache import ExactCache
from aegis.gateway.metering import MeteringRecorder
from aegis.gateway.providers.anthropic import AnthropicProvider
from aegis.gateway.providers.base import Provider
from aegis.gateway.providers.openai_compat import OpenAICompatProvider
from aegis.gateway.ratelimit import RateLimiter
from aegis.gateway.router import GatewayLimits, LLMGateway, parse_routes


def build_gateway() -> LLMGateway:
    s = get_settings()
    providers: dict[str, Provider] = {
        "bailian": OpenAICompatProvider(
            "bailian", s.dashscope_base_url, s.dashscope_api_key.get_secret_value()
        ),
        "anthropic": AnthropicProvider(
            "anthropic", s.anthropic_base_url, s.anthropic_api_key.get_secret_value()
        ),
    }
    redis = get_redis()
    return LLMGateway(
        providers=providers,
        routes=parse_routes(s.model_routes, set(providers)),
        breaker=CircuitBreaker(redis),
        limiter=RateLimiter(redis, replicas=s.replica_count),
        cache=ExactCache(redis, ttl_seconds=s.cache_ttl_seconds)
        if s.cache_ttl_seconds > 0
        else None,
        limits=GatewayLimits(
            provider_rate=s.provider_rate,
            provider_burst=s.provider_burst,
            tenant_rate=s.tenant_rate,
            tenant_burst=s.tenant_burst,
            max_wait=s.limiter_max_wait,
        ),
        fault_rate=s.fault_injection_rate,
        fault_targets=frozenset(s.fault_injection_targets),
        fault_mode=s.fault_injection_mode,
        meter=MeteringRecorder(
            get_session_factory(),
            {m: (Decimal(str(p)), Decimal(str(c))) for m, (p, c) in s.model_prices.items()},
        ),
        monthly_token_budget=s.tenant_monthly_token_budget,
        request_token_budget=s.request_token_budget,
    )

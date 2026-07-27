"""组装在边缘：真实依赖只在这里聚合成完整网关，其余代码一律靠注入。"""

from decimal import Decimal

import httpx
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aegis.core.config import get_settings
from aegis.core.db import get_session_factory
from aegis.core.redis import get_redis
from aegis.core.tenancy import TenantDirectory
from aegis.gateway.breaker import CircuitBreaker
from aegis.gateway.cache import ExactCache
from aegis.gateway.embeddings import EmbeddingClient
from aegis.gateway.metering import MeteringRecorder, PriceTable
from aegis.gateway.providers.anthropic import AnthropicProvider
from aegis.gateway.providers.base import Provider
from aegis.gateway.providers.openai_compat import OpenAICompatProvider
from aegis.gateway.ratelimit import RateLimiter
from aegis.gateway.router import GatewayLimits, LLMGateway, parse_routes


def _price_table(raw: dict[str, list[float]]) -> PriceTable:
    """Settings 的 float 报价一次性转 Decimal（str 中转防二进制尾差）——组装边缘唯一转换点。"""
    return {m: (Decimal(str(p)), Decimal(str(c))) for m, (p, c) in raw.items()}


def build_gateway(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    redis: aioredis.Redis | None = None,
    client: httpx.AsyncClient | None = None,
) -> LLMGateway:
    """真实网关组装。三参数全缺省 None=API 进程用进程单例（现行为零改动）；
    worker 每任务 asyncio.run 新 loop，三单例（get_session_factory/get_redis/
    shared_client）都绑创建时的 loop——任务体传任务局部实例（M3.9④ 受控缝，
    build_embedding_client 双参数化同款工程）。"""
    s = get_settings()
    sf = session_factory or get_session_factory()
    r = redis if redis is not None else get_redis()
    providers: dict[str, Provider] = {
        "bailian": OpenAICompatProvider(
            "bailian", s.dashscope_base_url, s.dashscope_api_key.get_secret_value(), client=client
        ),
        "anthropic": AnthropicProvider(
            "anthropic", s.anthropic_base_url, s.anthropic_api_key.get_secret_value(), client=client
        ),
    }
    return LLMGateway(
        providers=providers,
        routes=parse_routes(s.model_routes, set(providers)),
        breaker=CircuitBreaker(r),
        limiter=RateLimiter(r, replicas=s.replica_count),
        cache=ExactCache(r, ttl_seconds=s.cache_ttl_seconds) if s.cache_ttl_seconds > 0 else None,
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
        meter=MeteringRecorder(sf, _price_table(s.model_prices)),
        monthly_token_budget=s.tenant_monthly_token_budget,
        monthly_budget_resolver=TenantDirectory(sf).monthly_budget,
        request_token_budget=s.request_token_budget,
    )


def build_embedding_client(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    client: httpx.AsyncClient | None = None,
) -> EmbeddingClient:
    """embedding 通道组装（M3.4 D5）。两个参数化都是 Celery 跨 event loop 防炸（决策 C）：
    任务每次 asyncio.run 新建 loop，全局 DB 连接池与 shared_client 的 keep-alive 连接
    都绑着创建时的 loop——worker 必须同时传任务局部 session_factory 与任务局部
    AsyncClient（任务 async 入口内建、finally aclose）；缺省 None=API 进程（M3.5）用全局。
    RLS 前提：本工厂的账本走 aegis_app 低权引擎——调用方必须在 tenant_context(tenant_id)
    内执行 embed，否则计量 INSERT 被 WITH CHECK 拒绝、再被 fail-open 吞掉（只剩告警）。
    limiter 暂不接（决策 C：worker 批次串行天然限速；M3.5 查询侧接线时再议）。"""
    s = get_settings()
    sf = session_factory or get_session_factory()
    return EmbeddingClient(
        base_url=s.dashscope_base_url,
        api_key=s.dashscope_api_key.get_secret_value(),
        meter=MeteringRecorder(sf, _price_table(s.model_prices)),
        client=client,
    )

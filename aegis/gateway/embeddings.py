"""L1 受控扩展第二处（D5）：embedding 独立通道——不动 LLMGateway.complete。

为什么独立类：embedding 无档位路由/无流式/无缓存/无熔断语义，塞进 LLMGateway
会污染判别联合契约（plans/m3-detailed §3.3 D5）。与 chat 通道共享三样东西：
状态码翻译表（providers.base.raise_for_status）、共享 HTTP 客户端、计量账本。
重试口径：非流式请求-响应、读语义幂等——整调用可安全重试（区别于 chat 的
"只在首块前"铁律），白名单与退避公式复用 resilience 的同一把尺，不双维护；
AuthError/BadRequest 是配置/请求问题，不重试。
计量 fail-open：记账失败绝不拖垮摄取（缓存计量同款哲学），缺口由对账脚本暴露。
"""

import asyncio
import logging
from collections.abc import Sequence
from typing import Protocol
from uuid import uuid4

import httpx

from aegis.gateway.errors import (
    AuthError,
    GatewayOverloadedError,
    ProviderServerError,
    ProviderTimeoutError,
    RateLimitedError,
)
from aegis.gateway.providers.base import raise_for_status, shared_client
from aegis.gateway.resilience import RETRYABLE_ERRORS, RetryPolicy, compute_backoff
from aegis.gateway.router import LimiterLike

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 10
"""单次 /embeddings 的输入条数上限（§3.5 留白起步值，按百炼文档+实测调）。"""

_PROVIDER = "bailian-embed"
"""异常与限流 scope 里的身份名：与 chat 通道的 "bailian" 分账（各有各的桶与账目）。"""

# 出站限流参数（limiter 在场才消费）：v1 常量起步，M3.5 查询侧接线时再议是否升 Settings
_EMBED_RATE = 8.0
_EMBED_BURST = 16.0
_EMBED_MAX_WAIT = 10.0

_RETRY_POLICY = RetryPolicy()
"""只消费 max_attempts/base_backoff/max_backoff 三字段（流式专属字段对本通道无意义）。"""

_sleep = asyncio.sleep  # 测试接缝（resilience/ratelimit 同款）：替换这个名字，不打全局补丁


class EmbeddingMeterLike(Protocol):
    """计量面按形状注入（router.MeterLike 同款理由：测试替身不必背上真账本）。"""

    async def record_embedding(
        self, *, tenant_id: str, request_id: str, model: str, prompt_tokens: int, session_id: str | None = None
    ) -> None: ...


class EmbeddingClient:
    """text-embedding-v4 批量向量化：切批 → POST /embeddings → 按 index 归位 → 计量。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        meter: EmbeddingMeterLike | None = None,
        limiter: LimiterLike | None = None,
        client: httpx.AsyncClient | None = None,
        model: str = "text-embedding-v4",
        # 与 apps 层 EMBEDDING_DIMS 同值（相等性由 test_embeddings 跨层钉死；worker 装配显式传参）
        dimensions: int = 1024,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._meter = meter
        self._limiter = limiter
        self._client = client or shared_client()
        self._model = model
        self._dimensions = dimensions

    async def embed(self, texts: Sequence[str], *, tenant_id: str) -> list[list[float]]:
        """与输入同序同长的向量表。≤EMBED_BATCH_SIZE 条一批；空 key 抛 AuthError
        （openai_compat 同款快速失败）；批间串行——摄取是后台慢活，吞吐让位于简单。"""
        if isinstance(texts, str):  # str 本身满足 Sequence[str]——按字符逐个向量化是静默灾难
            raise TypeError("texts 需要字符串序列（list[str]），不要传单个字符串")
        if not self._api_key:
            raise AuthError(_PROVIDER, "API key 未配置（检查 .env 的 DASHSCOPE_API_KEY）")
        out: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            out.extend(await self._embed_batch(list(texts[start : start + EMBED_BATCH_SIZE]), tenant_id=tenant_id))
        return out

    async def _embed_batch(self, batch: list[str], *, tenant_id: str) -> list[list[float]]:
        """一批的有限退避重试壳：白名单/退避公式与 chat 通道同一把尺（resilience 复用）。"""
        attempt = 0
        while True:
            attempt += 1
            try:
                return await self._post_once(batch, tenant_id=tenant_id)
            except RETRYABLE_ERRORS as e:
                if attempt >= _RETRY_POLICY.max_attempts:
                    raise
                await _sleep(compute_backoff(attempt, _RETRY_POLICY, getattr(e, "retry_after", None)))

    async def _post_once(self, batch: list[str], *, tenant_id: str) -> list[list[float]]:
        if self._limiter is not None:
            ok = await self._limiter.wait_take(
                f"provider:{_PROVIDER}", _EMBED_RATE, _EMBED_BURST, max_wait=_EMBED_MAX_WAIT
            )
            if not ok:
                # 翻译成可重试族：等待预算耗尽与上游 429 对调用方是同一种事实——现在不许发
                raise RateLimitedError(_PROVIDER, "出站限流：等待预算内未获得令牌")
        try:
            resp = await self._client.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "input": batch,
                    "dimensions": self._dimensions,  # v4 多档输出，显式钉死（ADR-006）
                    "encoding_format": "float",  # 钉死浮点数组响应形态（上游缺省可能切 base64——形状校验的前提）
                },
            )
        except httpx.PoolTimeout as e:  # 本地过载单独分类（openai_compat 同款）：不记熔断账、不重试
            raise GatewayOverloadedError(f"[{_PROVIDER}] 本地连接池排队超时: {e!r}") from e
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(_PROVIDER, f"超时: {e!r}") from e
        except httpx.TransportError as e:
            raise ProviderServerError(_PROVIDER, f"连接失败: {e!r}") from e
        raise_for_status(_PROVIDER, resp)
        payload = resp.json()
        data = payload.get("data") or []
        if len(data) != len(batch):
            raise ProviderServerError(_PROVIDER, f"返回条数不符：期望 {len(batch)} 实得 {len(data)}")
        vectors: list[list[float]] = [[] for _ in batch]
        for item in data:  # 按 index 归位：上游不承诺顺序，错位向量=检索静默垃圾
            idx = item.get("index")
            vec = item.get("embedding") or []
            if not isinstance(idx, int) or not 0 <= idx < len(batch):
                raise ProviderServerError(_PROVIDER, f"非法 index: {idx!r}")
            if len(vec) != self._dimensions:
                raise ProviderServerError(_PROVIDER, f"维度不符：期望 {self._dimensions} 实得 {len(vec)}")
            vectors[idx] = [float(x) for x in vec]
        if any(len(v) != self._dimensions for v in vectors):
            raise ProviderServerError(_PROVIDER, "index 缺失/重复：有槽位未被填充")
        await self._record(tenant_id, payload)
        return vectors

    async def _record(self, tenant_id: str, payload: dict) -> None:
        """计量 fail-open：为了发票烧掉货物是荒唐的（router._safe_record 同款）。"""
        if self._meter is None:
            return
        usage = payload.get("usage") or {}
        try:
            await self._meter.record_embedding(
                tenant_id=tenant_id,
                request_id=uuid4().hex,
                model=payload.get("model", self._model),
                prompt_tokens=int(usage.get("prompt_tokens") or 0),  # or 0：上游 null 归零记行，不因畸形丢行
            )
        except Exception:
            logger.warning("embedding 计量失败（fail-open，缺口走 M1.12 对账）：tenant=%s", tenant_id, exc_info=True)

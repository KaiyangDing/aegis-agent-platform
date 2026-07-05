"""供应商适配器的公共契约与共享 HTTP 客户端。"""

from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from aegis.gateway.errors import (
    AuthError,
    BadRequestError,
    ProviderServerError,
    RateLimitedError,
)
from aegis.gateway.schema import LLMChunk, LLMRequest


class Provider(Protocol):
    """所有适配器的形状。路由(M1.9)只面向本协议编程，不认识任何具体适配器。"""

    name: str

    def complete(self, req: LLMRequest, model: str) -> AsyncIterator[LLMChunk]: ...


_client: httpx.AsyncClient | None = None


def shared_client() -> httpx.AsyncClient:
    """进程级单例：复用 keep-alive 连接池（架构 §6 三处连接池之一）。

    超时按用途分离：连接 5s（网不通要快速失败）、读取 90s（LLM 生成慢是正常的）。
    """
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=90.0, write=10.0, pool=5.0)
        )
    return _client


def raise_for_status(provider_name: str, resp: httpx.Response) -> None:
    """HTTP 状态码 → 分类异常的统一翻译表。所有适配器共用，防止两份表漂移。"""
    if resp.status_code < 400:
        return
    snippet = resp.text[:200]  # 错误体只留 200 字符：够排障，防日志爆炸
    if resp.status_code == 429:
        ra = resp.headers.get("Retry-After")
        raise RateLimitedError(provider_name, snippet, retry_after=float(ra) if ra else None)
    if resp.status_code in (401, 403):
        raise AuthError(provider_name, snippet)
    if resp.status_code >= 500:
        raise ProviderServerError(provider_name, f"HTTP {resp.status_code}: {snippet}")
    raise BadRequestError(provider_name, f"HTTP {resp.status_code}: {snippet}")

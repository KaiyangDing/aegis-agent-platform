"""供应商适配器的公共契约与共享 HTTP 客户端。"""

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol

import httpx

from aegis.gateway.errors import (
    AuthError,
    BadRequestError,
    ProviderServerError,
    ProviderTimeoutError,
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
    池上限显式写出（虽是 httpx 默认值）：它是背压刹车，PoolTimeout 的语义依赖这两个数。
    """
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=90.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
    return _client


_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{8,}")


def sanitize_error_text(text: str, limit: int = 200) -> str:
    """外部错误文本进入我们的异常前统一消毒：截断 + API key 模式打码。

    上游错误体不受我方控制：401 体惯例回显 key 片段（'Incorrect API key: sk-...'），
    400 体可能回显用户输入。异常文本会进日志与异常链（__cause__），
    是展示层 masker 罩不住的旁路——必须在源头消毒（审计加固 B）。
    """
    return _KEY_PATTERN.sub("sk-***", text[:limit])


def parse_retry_after(value: str | None) -> float | None:
    """Retry-After 按 RFC 7231 允许两种格式：秒数 或 HTTP-date。

    解析失败一律退化为 None（走指数退避）——外部输入永远不许把 ValueError
    裸穿进我们的异常体系（审计高危 #1：百炼入口的 envoy 代理就可能发日期格式）。
    """
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
        return max(0.0, (dt - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError):
        return None


def raise_for_status(provider_name: str, resp: httpx.Response) -> None:
    """HTTP 状态码 → 分类异常的统一翻译表。所有适配器共用，防止两份表漂移。

    与 02 §4 的重试白名单严格对齐：429/408/5xx 可重试类；501 归请求问题。
    """
    if resp.status_code < 400:
        return
    snippet = sanitize_error_text(resp.text)  # 截断 + key 打码：够排障，不泄密
    if resp.status_code == 429:
        raise RateLimitedError(
            provider_name, snippet, retry_after=parse_retry_after(resp.headers.get("Retry-After"))
        )
    if resp.status_code == 408:
        raise ProviderTimeoutError(provider_name, f"HTTP 408: {snippet}")
    if resp.status_code in (401, 403):
        raise AuthError(provider_name, snippet)
    if resp.status_code == 501:
        raise BadRequestError(provider_name, f"HTTP 501: {snippet}")  # 未实现≠上游故障
    if resp.status_code >= 500:
        raise ProviderServerError(provider_name, f"HTTP {resp.status_code}: {snippet}")
    raise BadRequestError(provider_name, f"HTTP {resp.status_code}: {snippet}")

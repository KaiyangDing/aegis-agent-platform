"""供应商适配器的公共契约与共享 HTTP 客户端。"""

from collections.abc import AsyncIterator
from typing import Protocol

import httpx

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

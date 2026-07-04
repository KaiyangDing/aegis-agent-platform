"""OpenAI 兼容适配器：覆盖阿里云百炼（Qwen/DeepSeek 系）。

职责边界：统一协议 ↔ OpenAI 线格式互译；HTTP 失败 ↔ 分类异常互译。
不做重试/熔断/路由——那是上层组件的事，本文件保持"笨"。
M1.2 范围：非流式、纯文本对话。流式在 M1.3，工具消息映射在 M1.4。
"""

from collections.abc import AsyncIterator
from typing import Literal

import httpx

from aegis.gateway.errors import (
    AuthError,
    BadRequestError,
    ProviderServerError,
    ProviderTimeoutError,
    RateLimitedError,
)
from aegis.gateway.providers.base import shared_client
from aegis.gateway.schema import (
    LLMChunk,
    LLMRequest,
    StopChunk,
    TextDelta,
    UsageChunk,
)

_FINISH_REASON_MAP: dict[str, Literal["end_turn", "tool_calls", "max_tokens"]] = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_calls",
}


class OpenAICompatProvider:
    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        client: httpx.AsyncClient | None = None,
    ):
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client or shared_client()

    async def complete(self, req: LLMRequest, model: str) -> AsyncIterator[LLMChunk]:
        if not self._api_key:
            raise AuthError(self.name, "API key 未配置（检查 .env 的 DASHSCOPE_API_KEY）")
        payload = self._build_payload(req, model)
        try:
            resp = await self._client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(self.name, f"超时: {e!r}") from e
        except httpx.TransportError as e:
            raise ProviderServerError(self.name, f"连接失败: {e!r}") from e
        self._raise_for_status(resp)

        data = resp.json()
        choice = data["choices"][0]
        text = choice["message"].get("content") or ""
        if text:
            # 非流式实现走同一个流式接口：全文就是一个大 delta（M1.3 换真流式，接口不变）
            yield TextDelta(text=text)
        usage = data.get("usage") or {}
        yield UsageChunk(
            model=data.get("model", model),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
        yield StopChunk(reason=_FINISH_REASON_MAP.get(choice.get("finish_reason"), "end_turn"))

    def _build_payload(self, req: LLMRequest, model: str) -> dict:
        messages = []
        for m in req.messages:
            if m.role == "tool" or m.tool_calls:
                raise NotImplementedError("工具消息的映射在 M1.4 实现")
            messages.append({"role": m.role, "content": m.content})
        payload: dict = {"model": model, "messages": messages, "stream": False}
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        if req.max_tokens is not None:
            payload["max_tokens"] = req.max_tokens
        return payload

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        snippet = resp.text[:200]  # 错误体只留 200 字符：够排障，防日志爆炸
        if resp.status_code == 429:
            ra = resp.headers.get("Retry-After")
            raise RateLimitedError(self.name, snippet, retry_after=float(ra) if ra else None)
        if resp.status_code in (401, 403):
            raise AuthError(self.name, snippet)
        if resp.status_code >= 500:
            raise ProviderServerError(self.name, f"HTTP {resp.status_code}: {snippet}")
        raise BadRequestError(self.name, f"HTTP {resp.status_code}: {snippet}")

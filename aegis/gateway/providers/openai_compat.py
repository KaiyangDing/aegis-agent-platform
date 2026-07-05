"""OpenAI 兼容适配器：覆盖阿里云百炼（Qwen/DeepSeek 系）。

职责边界：统一协议 ↔ OpenAI 线格式互译；HTTP 失败 ↔ 分类异常互译。
不做重试/熔断/路由——那是上层组件的事，本文件保持"笨"。
M1.3 起为真流式（SSE）；M1.4 起支持 tool-call 双向映射（增量碎片按 index 内部组装）。

对外不变量：chunk 顺序恒为 TextDelta* → ToolCallChunk* → UsageChunk → StopChunk；
文本逐块流式，工具调用整体交付。消费方可依赖此顺序。

对外不变量：chunk 流永远以 UsageChunk、StopChunk 依次收尾，消费方可依赖。
"""

import json
from collections.abc import AsyncIterator
from typing import Any, Literal

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
    Message,
    StopChunk,
    TextDelta,
    ToolCall,
    ToolCallChunk,
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

        usage: UsageChunk | None = None
        stop_reason: Literal["end_turn", "tool_calls", "max_tokens"] = "end_turn"
        pending: dict[int, dict[str, Any]] = {}  # index → 组装中的 tool_call
        try:
            async with self._client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            ) as resp:
                if resp.status_code >= 400:
                    # 流式模式下正文不自动加载，先显式读出来，错误详情才可用
                    await resp.aread()
                    self._raise_for_status(resp)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue  # 空行=事件分隔；": xx" 开头=服务器心跳注释，都合法
                    data_str = line[len("data:") :].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError as e:
                        raise ProviderServerError(self.name, f"SSE 坏行: {data_str[:120]}") from e

                    if event.get("usage"):
                        u = event["usage"]
                        usage = UsageChunk(
                            model=event.get("model", model),
                            prompt_tokens=u.get("prompt_tokens", 0),
                            completion_tokens=u.get("completion_tokens", 0),
                        )
                    choices = event.get("choices") or []
                    if not choices:
                        continue  # usage 专属事件的 choices 是空列表
                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    for frag in delta.get("tool_calls") or []:
                        idx = frag.get("index", 0)
                        slot = pending.setdefault(idx, {"id": "", "name": "", "args": []})
                        if frag.get("id"):
                            slot["id"] = frag["id"]
                        fn = frag.get("function") or {}
                        if fn.get("name"):
                            slot["name"] = fn["name"]
                        if fn.get("arguments"):
                            slot["args"].append(fn["arguments"])
                    text = delta.get("content") or ""
                    if text:
                        yield TextDelta(text=text)
                    fr = choice.get("finish_reason")
                    if fr:
                        stop_reason = _FINISH_REASON_MAP.get(fr, "end_turn")
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(self.name, f"超时: {e!r}") from e
        except httpx.TransportError as e:
            raise ProviderServerError(self.name, f"连接失败: {e!r}") from e

        # 不变量兑现：ToolCall* → Usage → Stop 收尾（文本已在循环中流出）
        for idx in sorted(pending):
            slot = pending[idx]
            yield ToolCallChunk(
                tool_call=ToolCall(
                    id=slot["id"] or f"call_{idx}",  # 个别兼容方言不发 id，兜底合成
                    name=slot["name"],
                    arguments_json="".join(slot["args"]),
                )
            )
        yield usage or UsageChunk(model=model, prompt_tokens=0, completion_tokens=0)
        yield StopChunk(reason=stop_reason)

    def _build_payload(self, req: LLMRequest, model: str) -> dict:
        payload: dict = {
            "model": model,
            "messages": [self._to_wire_message(m) for m in req.messages],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if req.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in req.tools
            ]
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        if req.max_tokens is not None:
            payload["max_tokens"] = req.max_tokens
        return payload

    def _to_wire_message(self, m: Message) -> dict:
        if m.role == "tool":
            return {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
        wire: dict = {"role": m.role, "content": m.content}
        if m.tool_calls:
            wire["content"] = m.content or None  # 纯工具轮 content 为空 → 线上惯例发 null
            wire["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments_json},
                }
                for tc in m.tool_calls
            ]
        return wire

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

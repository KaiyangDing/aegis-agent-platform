"""Anthropic Messages API 适配器（完整实现，桩测试验证——暂无真实 key，接入即用）。

与 OpenAI 方言的差异见各方法注释——这些差异正是统一协议存在的理由。
对外不变量与 openai_compat 完全一致：TextDelta* → ToolCallChunk* → Usage → Stop。
"""

import json
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx

from aegis.gateway.errors import (
    AuthError,
    BadRequestError,
    GatewayOverloadedError,
    ProviderServerError,
    ProviderTimeoutError,
)
from aegis.gateway.providers.base import raise_for_status, sanitize_error_text, shared_client
from aegis.gateway.schema import (
    LLMChunk,
    LLMRequest,
    StopChunk,
    TextDelta,
    ToolCall,
    ToolCallChunk,
    UsageChunk,
)

_STOP_REASON_MAP: dict[str, Literal["end_turn", "tool_calls", "max_tokens"]] = {
    "end_turn": "end_turn",
    "stop_sequence": "end_turn",
    "tool_use": "tool_calls",
    "max_tokens": "max_tokens",
}

DEFAULT_MAX_TOKENS = 4096  # Anthropic 强制必填；统一协议里可选，缺省时用这个


class AnthropicProvider:
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
            raise AuthError(self.name, "API key 未配置（.env 的 ANTHROPIC_API_KEY）")
        payload = self._build_payload(req, model)

        model_name = model
        input_tokens = 0
        output_tokens = 0
        stop_reason: Literal["end_turn", "tool_calls", "max_tokens"] = "end_turn"
        pending: dict[int, dict[str, Any]] = {}
        saw_stop = False  # 终止哨兵见证（与 openai_compat 的 saw_done 同款防线）
        try:
            async with self._client.stream(
                "POST",
                f"{self._base_url}/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                },
                json=payload,
            ) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    raise_for_status(self.name, resp)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue  # event:/空行——类型信息 data 里冗余存在，忽略无损
                    data_str = line[len("data:") :].strip()
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError as e:
                        raise ProviderServerError(
                            self.name, f"SSE 坏行: {sanitize_error_text(data_str, 120)}"
                        ) from e

                    etype = event.get("type")
                    if etype == "message_start":
                        msg = event.get("message") or {}
                        model_name = msg.get("model", model)
                        input_tokens = (msg.get("usage") or {}).get("input_tokens", 0)
                    elif etype == "content_block_start":
                        block = event.get("content_block") or {}
                        if block.get("type") == "tool_use":
                            pending[event.get("index", 0)] = {
                                "id": block.get("id", ""),
                                "name": block.get("name", ""),
                                "parts": [],
                            }
                    elif etype == "content_block_delta":
                        delta = event.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            text = delta.get("text") or ""
                            if text:
                                yield TextDelta(text=text)
                        elif delta.get("type") == "input_json_delta":
                            idx = event.get("index", 0)
                            if idx in pending and delta.get("partial_json"):
                                pending[idx]["parts"].append(delta["partial_json"])
                    elif etype == "message_delta":
                        d = event.get("delta") or {}
                        if d.get("stop_reason"):
                            stop_reason = _STOP_REASON_MAP.get(d["stop_reason"], "end_turn")
                        output_tokens = (event.get("usage") or {}).get(
                            "output_tokens", output_tokens
                        )
                    elif etype == "message_stop":
                        saw_stop = True
                        break
                    elif etype == "error":
                        err = event.get("error") or {}
                        detail = sanitize_error_text(str(err.get("message", "")), 120)
                        raise ProviderServerError(
                            self.name, f"流内错误 {err.get('type')}: {detail}"
                        )
                    # ping 等其余事件类型：无视
        except httpx.PoolTimeout as e:
            raise GatewayOverloadedError(f"[{self.name}] 本地连接池排队超时: {e!r}") from e
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(self.name, f"超时: {e!r}") from e
        except httpx.TransportError as e:
            raise ProviderServerError(self.name, f"连接失败: {e!r}") from e

        if not saw_stop:
            raise ProviderServerError(self.name, "流被截断：未收到 message_stop 终止哨兵")

        for idx in sorted(pending):
            slot = pending[idx]
            yield ToolCallChunk(
                tool_call=ToolCall(
                    id=slot["id"] or f"toolu_{idx}",
                    name=slot["name"],
                    arguments_json="".join(slot["parts"]),
                )
            )
        yield UsageChunk(
            model=model_name, prompt_tokens=input_tokens, completion_tokens=output_tokens
        )
        yield StopChunk(reason=stop_reason)

    def _build_payload(self, req: LLMRequest, model: str) -> dict:
        system_parts: list[str] = []
        messages: list[dict] = []
        for m in req.messages:
            if m.role == "system":
                system_parts.append(m.content)  # 差异：system 是顶层字段
            elif m.role == "tool":
                messages.append(
                    {
                        "role": "user",  # 差异：工具结果 = user 消息里的 tool_result 块
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.tool_call_id,
                                "content": m.content,
                            }
                        ],
                    }
                )
            elif m.tool_calls:
                blocks: list[dict] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": self._parse_args(tc),  # 差异：对象而非字符串
                        }
                    )
                messages.append({"role": "assistant", "content": blocks})
            else:
                messages.append({"role": m.role, "content": m.content})

        payload: dict = {
            "model": model,
            "messages": messages,
            "max_tokens": req.max_tokens or DEFAULT_MAX_TOKENS,  # 差异：强制必填
            "stream": True,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if req.tools:
            payload["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in req.tools
            ]
        if req.temperature is not None:
            payload["temperature"] = req.temperature
        return payload

    def _parse_args(self, tc: ToolCall) -> dict:
        try:
            return json.loads(tc.arguments_json) if tc.arguments_json else {}
        except json.JSONDecodeError as e:
            raise BadRequestError(
                self.name,
                f"历史 tool_call({tc.id}) 参数非法 JSON，无法转换为 Anthropic 格式",
            ) from e

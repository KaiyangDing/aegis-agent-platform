import json

import httpx
import pytest
import respx

from aegis.gateway.errors import (
    AuthError,
    BadRequestError,
    ProviderServerError,
    RateLimitedError,
)
from aegis.gateway.providers.anthropic import AnthropicProvider
from aegis.gateway.schema import (
    LLMRequest,
    Message,
    StopChunk,
    TextDelta,
    ToolCall,
    ToolCallChunk,
    ToolSpec,
    UsageChunk,
)

BASE = "https://fake-anthropic.test"
URL = f"{BASE}/v1/messages"
SSE_HEADERS = {"content-type": "text/event-stream"}


def sse(*events: dict) -> bytes:
    """Anthropic 风格：每个事件两行（event: + data:），事件间空行。"""
    out = []
    for e in events:
        out.append(f"event: {e.get('type', '?')}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n")
    return "".join(out).encode("utf-8")


MSG_START = {
    "type": "message_start",
    "message": {"model": "claude-sonnet-4", "usage": {"input_tokens": 25}},
}
MSG_DELTA_END = {
    "type": "message_delta",
    "delta": {"stop_reason": "end_turn"},
    "usage": {"output_tokens": 7},
}
MSG_STOP = {"type": "message_stop"}


def text_delta(s: str, idx: int = 0) -> dict:
    return {"type": "content_block_delta", "index": idx, "delta": {"type": "text_delta", "text": s}}


def make_provider(api_key: str = "sk-ant-test") -> AnthropicProvider:
    return AnthropicProvider(name="anthropic", base_url=BASE, api_key=api_key)


def make_req() -> LLMRequest:
    return LLMRequest(tier="standard", tenant_id="t1", messages=[Message(role="user", content="你好")])


async def collect(provider: AnthropicProvider, req: LLMRequest) -> list:
    return [c async for c in provider.complete(req, model="claude-sonnet-4")]


@respx.mock
async def test_payload_system_extracted_and_auth_headers():
    route = respx.post(URL).mock(return_value=httpx.Response(200, content=sse(MSG_STOP), headers=SSE_HEADERS))
    req = LLMRequest(
        tier="standard",
        tenant_id="t1",
        messages=[
            Message(role="system", content="你是客服。"),
            Message(role="user", content="你好"),
        ],
    )
    await collect(make_provider(), req)
    sent = json.loads(route.calls.last.request.content)
    assert sent["system"] == "你是客服。"
    assert sent["messages"] == [{"role": "user", "content": "你好"}]  # system 不进 messages
    assert sent["max_tokens"] == 4096  # 未指定时的强制默认
    headers = route.calls.last.request.headers
    assert headers["x-api-key"] == "sk-ant-test"
    assert headers["anthropic-version"] == "2023-06-01"


@respx.mock
async def test_payload_tools_use_input_schema():
    route = respx.post(URL).mock(return_value=httpx.Response(200, content=sse(MSG_STOP), headers=SSE_HEADERS))
    req = LLMRequest(
        tier="standard",
        tenant_id="t1",
        messages=[Message(role="user", content="天气")],
        tools=[ToolSpec(name="get_weather", description="查天气", parameters={"type": "object"})],
    )
    await collect(make_provider(), req)
    sent = json.loads(route.calls.last.request.content)
    assert sent["tools"] == [{"name": "get_weather", "description": "查天气", "input_schema": {"type": "object"}}]


@respx.mock
async def test_payload_tool_round_history_converted():
    route = respx.post(URL).mock(return_value=httpx.Response(200, content=sse(MSG_STOP), headers=SSE_HEADERS))
    req = LLMRequest(
        tier="standard",
        tenant_id="t1",
        messages=[
            Message(role="user", content="查订单"),
            Message(
                role="assistant",
                tool_calls=[ToolCall(id="toolu_1", name="order_query", arguments_json='{"order_id":"A1"}')],
            ),
            Message(role="tool", tool_call_id="toolu_1", content='{"status":"shipped"}'),
        ],
    )
    await collect(make_provider(), req)
    sent = json.loads(route.calls.last.request.content)
    assert sent["messages"][1] == {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "order_query",
                "input": {"order_id": "A1"},  # 字符串被 parse 成了对象
            }
        ],
    }
    assert sent["messages"][2] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": '{"status":"shipped"}'}],
    }


async def test_bad_history_arguments_fail_loudly():
    req = LLMRequest(
        tier="standard",
        tenant_id="t1",
        messages=[
            Message(role="user", content="查"),
            Message(
                role="assistant",
                tool_calls=[ToolCall(id="x", name="f", arguments_json="{坏json")],
            ),
        ],
    )
    with pytest.raises(BadRequestError):
        await collect(make_provider(), req)


@respx.mock
async def test_stream_text_and_usage_merged_from_two_places():
    body = sse(MSG_START, text_delta("你"), text_delta("好"), MSG_DELTA_END, MSG_STOP)
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    chunks = await collect(make_provider(), make_req())
    assert chunks == [
        TextDelta(text="你"),
        TextDelta(text="好"),
        UsageChunk(model="claude-sonnet-4", prompt_tokens=25, completion_tokens=7),
        StopChunk(reason="end_turn"),
    ]


@respx.mock
async def test_stream_tool_use_assembled_from_partial_json():
    body = sse(
        MSG_START,
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "toolu_9", "name": "get_weather"},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"ci'},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": 'ty":"杭州"}'},
        },
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {"output_tokens": 30},
        },
        MSG_STOP,
    )
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    chunks = await collect(make_provider(), make_req())
    assert chunks == [
        ToolCallChunk(tool_call=ToolCall(id="toolu_9", name="get_weather", arguments_json='{"city":"杭州"}')),
        UsageChunk(model="claude-sonnet-4", prompt_tokens=25, completion_tokens=30),
        StopChunk(reason="tool_calls"),  # tool_use → 统一协议的 tool_calls
    ]


@respx.mock
async def test_in_stream_error_event_raises():
    body = sse(
        MSG_START,
        {"type": "error", "error": {"type": "overloaded_error", "message": "服务过载"}},
    )
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    with pytest.raises(ProviderServerError):
        await collect(make_provider(), make_req())


@respx.mock
async def test_ping_and_unknown_events_ignored():
    body = sse(MSG_START, {"type": "ping"}, text_delta("嗨"), MSG_DELTA_END, MSG_STOP)
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    chunks = await collect(make_provider(), make_req())
    assert chunks[0] == TextDelta(text="嗨")


@respx.mock
async def test_429_via_shared_raise_for_status():
    respx.post(URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "2"}, text="busy"))
    with pytest.raises(RateLimitedError) as ei:
        await collect(make_provider(), make_req())
    assert ei.value.retry_after == 2.0
    assert ei.value.provider == "anthropic"


@respx.mock
async def test_401_maps_to_auth_error():
    respx.post(URL).mock(return_value=httpx.Response(401, text="invalid x-api-key"))
    with pytest.raises(AuthError):
        await collect(make_provider(), make_req())


async def test_empty_api_key_fails_fast():
    with pytest.raises(AuthError):
        await collect(make_provider(api_key=""), make_req())


# ---------- 审计加固 A ----------


@respx.mock
async def test_stream_without_message_stop_is_truncation():
    body = sse(MSG_START, text_delta("半"))  # 干净断连：没有 message_stop
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    got = []
    with pytest.raises(ProviderServerError):
        async for c in make_provider().complete(make_req(), model="claude-sonnet-4"):
            got.append(c)
    assert got == [TextDelta(text="半")]

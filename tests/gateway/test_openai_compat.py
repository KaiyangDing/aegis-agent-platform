import json

import httpx
import pytest
import respx

from aegis.gateway.errors import (
    AuthError,
    BadRequestError,
    GatewayOverloadedError,
    ProviderServerError,
    ProviderTimeoutError,
    RateLimitedError,
)
from aegis.gateway.providers.openai_compat import OpenAICompatProvider
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

BASE = "https://fake-bailian.test/v1"
URL = f"{BASE}/chat/completions"
SSE_HEADERS = {"content-type": "text/event-stream"}


def sse(*events: dict | str) -> bytes:
    """把若干事件拼成 SSE 线格式正文（dict 自动转 JSON，str 原样放入）。"""
    out = []
    for e in events:
        payload = e if isinstance(e, str) else json.dumps(e, ensure_ascii=False)
        out.append(f"data: {payload}\n\n")
    return "".join(out).encode("utf-8")


def text_event(s: str) -> dict:
    return {"choices": [{"delta": {"content": s}}]}


FINISH_EVENT = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
USAGE_EVENT = {
    "choices": [],
    "model": "qwen-flash",
    "usage": {"prompt_tokens": 12, "completion_tokens": 5},
}


def make_provider(api_key: str = "sk-test") -> OpenAICompatProvider:
    return OpenAICompatProvider(name="bailian", base_url=BASE, api_key=api_key)


def make_req() -> LLMRequest:
    return LLMRequest(tier="fast", tenant_id="t1", messages=[Message(role="user", content="你好")])


async def collect(provider: OpenAICompatProvider, req: LLMRequest) -> list:
    return [c async for c in provider.complete(req, model="qwen-flash")]


@respx.mock
async def test_payload_requests_streaming_with_usage():
    route = respx.post(URL).mock(
        return_value=httpx.Response(200, content=sse("[DONE]"), headers=SSE_HEADERS)
    )
    await collect(make_provider(), make_req())
    sent = json.loads(route.calls.last.request.content)
    assert sent["stream"] is True
    assert sent["stream_options"] == {"include_usage": True}
    assert sent["messages"] == [{"role": "user", "content": "你好"}]
    assert route.calls.last.request.headers["Authorization"] == "Bearer sk-test"


@respx.mock
async def test_deltas_stream_and_tail_is_usage_then_stop():
    # 线上顺序是 finish 在前、usage 在后；我们的不变量要求输出以 Usage→Stop 收尾
    body = sse(text_event("你"), text_event("好"), FINISH_EVENT, USAGE_EVENT, "[DONE]")
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    chunks = await collect(make_provider(), make_req())
    assert chunks == [
        TextDelta(text="你"),
        TextDelta(text="好"),
        UsageChunk(model="qwen-flash", prompt_tokens=12, completion_tokens=5),
        StopChunk(reason="end_turn"),
    ]


@respx.mock
async def test_role_prelude_and_empty_delta_produce_no_text():
    body = sse(
        {"choices": [{"delta": {"role": "assistant", "content": ""}}]},
        {"choices": [{"delta": {}}]},
        "[DONE]",
    )
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    chunks = await collect(make_provider(), make_req())
    assert chunks == [
        UsageChunk(model="qwen-flash", prompt_tokens=0, completion_tokens=0),
        StopChunk(reason="end_turn"),
    ]


@respx.mock
async def test_done_sentinel_stops_reading():
    # [DONE] 之后的坏行不应被解析（如果被解析，会抛 ProviderServerError 导致本测试失败）
    body = sse(text_event("hi"), "[DONE]", "{{{ 这不是合法 JSON")
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    chunks = await collect(make_provider(), make_req())
    assert chunks[0] == TextDelta(text="hi")


@respx.mock
async def test_missing_usage_still_ends_with_usage_and_stop():
    body = sse(text_event("嗨"), FINISH_EVENT, "[DONE]")
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    chunks = await collect(make_provider(), make_req())
    assert chunks[-2] == UsageChunk(model="qwen-flash", prompt_tokens=0, completion_tokens=0)
    assert chunks[-1] == StopChunk(reason="end_turn")


@respx.mock
async def test_malformed_line_before_done_raises_server_error():
    body = sse(text_event("好"), "{{{ 坏行")
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    with pytest.raises(ProviderServerError):
        await collect(make_provider(), make_req())


class ExplodingStream(httpx.AsyncByteStream):
    """吐出半截内容后模拟连接断开——中途断线的最小复现。"""

    async def __aiter__(self):
        yield sse(text_event("half"))
        raise httpx.ReadError("connection lost")


@respx.mock
async def test_midstream_disconnect_after_partial_output():
    respx.post(URL).mock(
        return_value=httpx.Response(200, stream=ExplodingStream(), headers=SSE_HEADERS)
    )
    got = []
    with pytest.raises(ProviderServerError):
        async for c in make_provider().complete(make_req(), model="qwen-flash"):
            got.append(c)
    # 半截输出已经流出去了——这就是 03 §5"半截 llm_call"要处理的现实，M2 见
    assert got == [TextDelta(text="half")]


@respx.mock
async def test_429_maps_to_rate_limited_with_retry_after():
    respx.post(URL).mock(
        return_value=httpx.Response(429, headers={"Retry-After": "3"}, text="busy")
    )
    with pytest.raises(RateLimitedError) as ei:
        await collect(make_provider(), make_req())
    assert ei.value.retry_after == 3.0


@respx.mock
async def test_5xx_maps_to_server_error():
    respx.post(URL).mock(return_value=httpx.Response(503, text="upstream down"))
    with pytest.raises(ProviderServerError):
        await collect(make_provider(), make_req())


@respx.mock
async def test_401_maps_to_auth_error():
    respx.post(URL).mock(return_value=httpx.Response(401, text="invalid key"))
    with pytest.raises(AuthError):
        await collect(make_provider(), make_req())


@respx.mock
async def test_other_4xx_maps_to_bad_request():
    respx.post(URL).mock(return_value=httpx.Response(400, text="model not found"))
    with pytest.raises(BadRequestError):
        await collect(make_provider(), make_req())


@respx.mock
async def test_connect_timeout_maps_to_timeout_error():
    respx.post(URL).mock(side_effect=httpx.ReadTimeout("boom"))
    with pytest.raises(ProviderTimeoutError):
        await collect(make_provider(), make_req())


async def test_empty_api_key_fails_fast_without_any_network():
    with pytest.raises(AuthError):
        await collect(make_provider(api_key=""), make_req())


# ---------- M1.4 工具映射 ----------

WEATHER_TOOL = ToolSpec(
    name="get_weather",
    description="查天气",
    parameters={"type": "object", "properties": {"city": {"type": "string"}}},
)


def tc_frag(
    index: int, *, id: str | None = None, name: str | None = None, args: str | None = None
) -> dict:
    fn: dict = {}
    if name is not None:
        fn["name"] = name
    if args is not None:
        fn["arguments"] = args
    frag: dict = {"index": index, "function": fn}
    if id is not None:
        frag["id"] = id
    return frag


def tool_event(*frags: dict) -> dict:
    return {"choices": [{"delta": {"tool_calls": list(frags)}}]}


@respx.mock
async def test_tools_spec_mapped_into_payload():
    route = respx.post(URL).mock(
        return_value=httpx.Response(200, content=sse("[DONE]"), headers=SSE_HEADERS)
    )
    req = LLMRequest(
        tier="fast",
        tenant_id="t1",
        messages=[Message(role="user", content="天气")],
        tools=[WEATHER_TOOL],
    )
    await collect(make_provider(), req)
    sent = json.loads(route.calls.last.request.content)
    assert sent["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "查天气",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
            },
        }
    ]


@respx.mock
async def test_tool_round_history_mapped_to_wire():
    route = respx.post(URL).mock(
        return_value=httpx.Response(200, content=sse("[DONE]"), headers=SSE_HEADERS)
    )
    req = LLMRequest(
        tier="fast",
        tenant_id="t1",
        messages=[
            Message(role="user", content="查订单"),
            Message(
                role="assistant",
                tool_calls=[
                    ToolCall(id="call_7", name="order_query", arguments_json='{"order_id":"A1"}')
                ],
            ),
            Message(role="tool", tool_call_id="call_7", content='{"status":"shipped"}'),
        ],
    )
    await collect(make_provider(), req)
    sent = json.loads(route.calls.last.request.content)
    assert sent["messages"][1] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_7",
                "type": "function",
                "function": {"name": "order_query", "arguments": '{"order_id":"A1"}'},
            }
        ],
    }
    assert sent["messages"][2] == {
        "role": "tool",
        "tool_call_id": "call_7",
        "content": '{"status":"shipped"}',
    }


@respx.mock
async def test_streaming_fragments_assemble_into_whole_tool_call():
    body = sse(
        tool_event(tc_frag(0, id="call_9", name="get_weather", args="")),
        tool_event(tc_frag(0, args='{"ci')),
        tool_event(tc_frag(0, args='ty":"杭州"}')),
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
        "[DONE]",
    )
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    chunks = await collect(make_provider(), make_req())
    assert chunks == [
        ToolCallChunk(
            tool_call=ToolCall(id="call_9", name="get_weather", arguments_json='{"city":"杭州"}')
        ),
        UsageChunk(model="qwen-flash", prompt_tokens=0, completion_tokens=0),
        StopChunk(reason="tool_calls"),
    ]


@respx.mock
async def test_parallel_tool_calls_keep_index_order():
    body = sse(
        tool_event(tc_frag(0, id="a", name="f1", args='{"x":1}')),
        tool_event(tc_frag(1, id="b", name="f2", args='{"y":2}')),
        tool_event(tc_frag(0, args=" ")),  # 碎片乱序交错：按 index 聚合，不按到达顺序
        "[DONE]",
    )
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    chunks = await collect(make_provider(), make_req())
    tool_chunks = [c for c in chunks if isinstance(c, ToolCallChunk)]
    assert [c.tool_call.id for c in tool_chunks] == ["a", "b"]
    assert tool_chunks[0].tool_call.arguments_json == '{"x":1} '


@respx.mock
async def test_text_then_tool_calls_respect_chunk_order_invariant():
    body = sse(
        text_event("我来查一下。"),
        tool_event(tc_frag(0, id="c", name="get_weather", args="{}")),
        "[DONE]",
    )
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    chunks = await collect(make_provider(), make_req())
    assert [type(c).__name__ for c in chunks] == [
        "TextDelta",
        "ToolCallChunk",
        "UsageChunk",
        "StopChunk",
    ]


# ---------- 审计加固 A ----------


@respx.mock
async def test_retry_after_http_date_maps_to_seconds():
    respx.post(URL).mock(
        return_value=httpx.Response(
            429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, text="busy"
        )
    )
    with pytest.raises(RateLimitedError) as ei:
        await collect(make_provider(), make_req())
    # HTTP-date 被换算成秒数（过去的日期钳位为 0），绝不允许 ValueError 裸穿三层防线
    assert ei.value.retry_after is not None
    assert ei.value.retry_after >= 0.0


@respx.mock
async def test_retry_after_garbage_degrades_to_none():
    respx.post(URL).mock(
        return_value=httpx.Response(429, headers={"Retry-After": "soon-ish"}, text="busy")
    )
    with pytest.raises(RateLimitedError) as ei:
        await collect(make_provider(), make_req())
    assert ei.value.retry_after is None  # 解析不了就退化为指数退避，不炸


@respx.mock
async def test_pool_timeout_is_local_overload_not_provider_fault():
    respx.post(URL).mock(side_effect=httpx.PoolTimeout("pool exhausted"))
    with pytest.raises(GatewayOverloadedError):
        await collect(make_provider(), make_req())


@respx.mock
async def test_in_stream_error_event_raises():
    body = sse({"error": {"code": "internal_error", "message": "server exploded"}})
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    with pytest.raises(ProviderServerError):
        await collect(make_provider(), make_req())


@respx.mock
async def test_stream_without_done_sentinel_is_truncation():
    body = sse(text_event("半截"))  # 干净断连：没有 [DONE]
    respx.post(URL).mock(return_value=httpx.Response(200, content=body, headers=SSE_HEADERS))
    got = []
    with pytest.raises(ProviderServerError):
        async for c in make_provider().complete(make_req(), model="qwen-flash"):
            got.append(c)
    assert got == [TextDelta(text="半截")]  # 已流出的不收回，但绝不合成完整收尾


@respx.mock
async def test_empty_200_body_is_truncation_not_success():
    respx.post(URL).mock(return_value=httpx.Response(200, content=b"", headers=SSE_HEADERS))
    with pytest.raises(ProviderServerError):
        await collect(make_provider(), make_req())

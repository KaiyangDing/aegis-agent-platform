import json

import httpx
import pytest
import respx

from aegis.gateway.errors import (
    AuthError,
    BadRequestError,
    ProviderServerError,
    ProviderTimeoutError,
    RateLimitedError,
)
from aegis.gateway.providers.openai_compat import OpenAICompatProvider
from aegis.gateway.schema import LLMRequest, Message, StopChunk, TextDelta, UsageChunk

BASE = "https://fake-bailian.test/v1"
URL = f"{BASE}/chat/completions"

OK_BODY = {
    "model": "qwen-flash",
    "choices": [{"message": {"role": "assistant", "content": "你好！"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 12, "completion_tokens": 5},
}


def make_provider(api_key: str = "sk-test") -> OpenAICompatProvider:
    return OpenAICompatProvider(name="bailian", base_url=BASE, api_key=api_key)


def make_req() -> LLMRequest:
    return LLMRequest(tier="fast", tenant_id="t1", messages=[Message(role="user", content="你好")])


async def collect(provider: OpenAICompatProvider, req: LLMRequest) -> list:
    return [c async for c in provider.complete(req, model="qwen-flash")]


@respx.mock
async def test_payload_carries_model_messages_and_auth():
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=OK_BODY))
    await collect(make_provider(), make_req())
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "qwen-flash"
    assert sent["messages"] == [{"role": "user", "content": "你好"}]
    assert route.calls.last.request.headers["Authorization"] == "Bearer sk-test"


@respx.mock
async def test_ok_response_becomes_three_chunks():
    respx.post(URL).mock(return_value=httpx.Response(200, json=OK_BODY))
    chunks = await collect(make_provider(), make_req())
    assert chunks == [
        TextDelta(text="你好！"),
        UsageChunk(model="qwen-flash", prompt_tokens=12, completion_tokens=5),
        StopChunk(reason="end_turn"),
    ]


@respx.mock
async def test_429_maps_to_rate_limited_with_retry_after():
    respx.post(URL).mock(
        return_value=httpx.Response(429, headers={"Retry-After": "3"}, text="busy")
    )
    with pytest.raises(RateLimitedError) as ei:
        await collect(make_provider(), make_req())
    assert ei.value.retry_after == 3.0
    assert ei.value.provider == "bailian"


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
async def test_read_timeout_maps_to_timeout_error():
    respx.post(URL).mock(side_effect=httpx.ReadTimeout("boom"))
    with pytest.raises(ProviderTimeoutError):
        await collect(make_provider(), make_req())


async def test_empty_api_key_fails_fast_without_any_network():
    with pytest.raises(AuthError):
        await collect(make_provider(api_key=""), make_req())

"""M3.4 交付②：EmbeddingClient（D5 受控缝第二处）——respx 桩驱动，零真实调用。

契约面：切批 ≤EMBED_BATCH_SIZE、payload 四键（model/input/dimensions/encoding_format）、
按 index 归位（上游顺序不承诺）、429/5xx/传输错误有限退避重试（读语义幂等、与 chat
通道同一把退避尺）、AuthError/BadRequest 不重试、形状校验 fail-loud、计量 fail-open。
"""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from aegis.gateway import embeddings
from aegis.gateway.embeddings import EmbeddingClient
from aegis.gateway.errors import (
    AuthError,
    BadRequestError,
    ProviderServerError,
    RateLimitedError,
)
from aegis.gateway.factory import build_embedding_client
from aegis.gateway.metering import MeteringRecorder, PriceTable, UsageRecord

BASE = "https://fake-bailian.test/v1"
URL = f"{BASE}/embeddings"


def ok_payload(
    n: int,
    *,
    dims: int = 1024,
    model: str = "text-embedding-v4",
    prompt_tokens: int = 7,
    reverse: bool = False,
) -> dict:
    """OpenAI 兼容 /embeddings 响应体；reverse=True 模拟上游乱序返回（index 归位的对抗面）。"""
    idxs = list(range(n))
    if reverse:
        idxs.reverse()
    return {
        "object": "list",
        "data": [{"object": "embedding", "index": i, "embedding": [float(i)] * dims} for i in idxs],
        "model": model,
        "usage": {"prompt_tokens": prompt_tokens, "total_tokens": prompt_tokens},
    }


def make_client(api_key: str = "sk-test", **kw) -> EmbeddingClient:
    return EmbeddingClient(base_url=BASE, api_key=api_key, **kw)


@pytest.fixture
def no_sleep(monkeypatch):
    """退避不真睡（00 §2.2 时序纪律）：记录每次退避时长供断言。"""
    slept: list[float] = []

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr(embeddings, "_sleep", fake_sleep)
    return slept


@respx.mock
async def test_batches_payload_and_order():
    """25 条 → 3 批（10/10/5）；payload 四键与鉴权头；第二批乱序返回仍按 index 归位到全局顺序。"""
    texts = [f"块{i}" for i in range(25)]
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(200, json=ok_payload(10)),
            httpx.Response(200, json=ok_payload(10, reverse=True)),
            httpx.Response(200, json=ok_payload(5)),
        ]
    )
    out = await make_client().embed(texts, tenant_id="t-emb")
    assert route.call_count == 3
    first = json.loads(route.calls[0].request.content)
    expected = {"model": "text-embedding-v4", "input": texts[:10], "dimensions": 1024, "encoding_format": "float"}
    assert first == expected
    assert route.calls[0].request.headers["Authorization"] == "Bearer sk-test"
    assert len(out) == 25 and all(len(v) == 1024 for v in out)
    assert out[13][0] == 3.0 and out[24][0] == 4.0  # 批内 index → 全局位置（10+3 / 20+4）


@respx.mock
async def test_empty_input_returns_empty_without_http():
    """空输入零 HTTP：respx 无路由，若发请求会当场炸——通过即证明没发。"""
    assert await make_client().embed([], tenant_id="t") == []


@respx.mock
async def test_empty_key_is_config_error_before_any_http():
    """空 key = 配置错误，进任何网络动作之前快速失败（openai_compat 同款防线）。"""
    with pytest.raises(AuthError):
        await make_client(api_key="").embed(["x"], tenant_id="t")


@respx.mock
async def test_429_backoff_prefers_retry_after(no_sleep):
    """429 重试且退避服从服务端 Retry-After（compute_backoff 复用——与 chat 同一把尺）。"""
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2"}, json={"error": "throttled"}),
            httpx.Response(200, json=ok_payload(1)),
        ]
    )
    out = await make_client().embed(["x"], tenant_id="t")
    assert len(out) == 1 and route.call_count == 2
    assert no_sleep == [2.0]


@respx.mock
async def test_server_error_exhausts_attempts(no_sleep):
    """5xx 有限重试：RetryPolicy.max_attempts 打满后原样上抛（预算与 chat 通道一致）。"""
    route = respx.post(URL).mock(return_value=httpx.Response(503, json={}))
    with pytest.raises(ProviderServerError):
        await make_client().embed(["x"], tenant_id="t")
    assert route.call_count == 3
    assert len(no_sleep) == 2  # 三次尝试之间恰两次退避


@respx.mock
async def test_bad_request_is_not_retried(no_sleep):
    """400 是请求问题不是上游故障：一次都不重试（白名单之外裸抛）。"""
    route = respx.post(URL).mock(return_value=httpx.Response(400, json={}))
    with pytest.raises(BadRequestError):
        await make_client().embed(["x"], tenant_id="t")
    assert route.call_count == 1 and no_sleep == []


@respx.mock
async def test_transport_error_translated_and_retried(no_sleep):
    """连接失败翻译成 ProviderServerError（可重试族）——httpx 异常不许裸穿出通道。"""
    route = respx.post(URL).mock(side_effect=httpx.ConnectError("拔网线"))
    with pytest.raises(ProviderServerError):
        await make_client().embed(["x"], tenant_id="t")
    assert route.call_count == 3


@respx.mock
@pytest.mark.parametrize("payload", [ok_payload(1, dims=8), ok_payload(2)], ids=["维度不符", "条数不符"])
async def test_shape_mismatch_fails_loud(no_sleep, payload):
    """形状校验 fail-loud：维度/条数不符的 200 是静默垃圾的源头，必须炸不许存。
    口径：畸形响应归 ProviderServerError（可重试族）——烧满重试预算后上抛，与 chat 通道对坏流的处置一致。"""
    route = respx.post(URL).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(ProviderServerError):
        await make_client().embed(["x"], tenant_id="t")
    assert route.call_count == 3  # 确定性畸形也走满预算——分类按"谁的错"不按"会不会好"


class _RejectingLimiter:
    """按 LimiterLike 形状的替身：恒拒绝，记录调用参数。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, float, float, float]] = []

    async def wait_take(
        self, scope: str, rate: float, capacity: float, *, max_wait: float = 10.0, cost: float = 1.0
    ) -> bool:
        self.calls.append((scope, rate, capacity, max_wait))
        return False


@respx.mock
async def test_limiter_rejection_is_rate_limited_before_http(no_sleep):
    """限流缝：拒绝翻译成 RateLimitedError（可重试族），HTTP 一次不发；scope 与 chat 分账。"""
    limiter = _RejectingLimiter()
    with pytest.raises(RateLimitedError):
        await make_client(limiter=limiter).embed(["x"], tenant_id="t")
    assert {c[0] for c in limiter.calls} == {"provider:bailian-embed"}
    assert len(limiter.calls) == 3  # 重试流量同样过闸


PRICES: PriceTable = {"text-embedding-v4": (Decimal("0.0005"), Decimal("0"))}


@respx.mock
async def test_metering_writes_embedding_row(db_session_factory):
    """计量行契约：tier="embedding" 自由字符串（Tier 是 chat 档位契约禁改）、
    completion=0、cost=输入价×token/1000 精确 Decimal（钱不过 float）。"""
    respx.post(URL).mock(return_value=httpx.Response(200, json=ok_payload(2, prompt_tokens=1000)))
    meter = MeteringRecorder(db_session_factory, PRICES)
    await make_client(meter=meter).embed(["a", "b"], tenant_id="t-emb-row")
    async with db_session_factory() as s:
        row = (await s.execute(select(UsageRecord).where(UsageRecord.tenant_id == "t-emb-row"))).scalar_one()
    assert (row.tier, row.provider, row.model) == ("embedding", "bailian", "text-embedding-v4")
    assert (row.prompt_tokens, row.completion_tokens, row.cached) == (1000, 0, False)
    assert row.cost == Decimal("0.0005")


class _BoomMeter:
    """按 EmbeddingMeterLike 形状的替身：恒炸——fail-open 面的对抗输入。"""

    async def record_embedding(
        self, *, tenant_id: str, request_id: str, model: str, prompt_tokens: int, session_id: str | None = None
    ) -> None:
        raise RuntimeError("账本挂了")


@respx.mock
async def test_metering_failure_is_fail_open(caplog):
    """记账失败绝不拖垮摄取（router._safe_record 同款哲学）：结果照常返回、告警留痕。"""
    respx.post(URL).mock(return_value=httpx.Response(200, json=ok_payload(1)))
    out = await make_client(meter=_BoomMeter()).embed(["x"], tenant_id="t")
    assert len(out) == 1
    assert "计量" in caplog.text


def test_default_dimensions_pins_apps_constant():
    """跨层一致性钉子：gateway 不许 import apps（层序），两处 1024 字面量靠本断言钉死同值。"""
    from aegis.apps.support.rag.models import EMBEDDING_DIMS  # 测试不受层契约约束，可同时够到两层

    assert make_client()._dimensions == EMBEDDING_DIMS


def test_build_embedding_client_session_factory_seam():
    """决策 C 组装缝：传入的任务局部工厂原样进 MeteringRecorder——跨 event loop 防炸第一条。"""
    sf = async_sessionmaker(expire_on_commit=False)  # 未绑引擎的工厂对象即可——组装缝只搬运引用
    client = build_embedding_client(session_factory=sf)
    assert isinstance(client._meter, MeteringRecorder)
    assert client._meter._sf is sf

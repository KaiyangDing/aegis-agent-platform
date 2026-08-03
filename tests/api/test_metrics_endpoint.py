"""M4.2 交付②：/metrics 端点 + HTTP 计数中间件 + chat 延迟打点。

时序数值零断言（红线 5）：只断 observe/inc 发生过与次数（样本计数），不断大小。
计数断言一律 delta 式（模块级 REGISTRY 跨测试常驻——M2.10 全库断言教训的指标版）；
chat 打点直测 `_relay`（帧序可控、零 LLM 桩装配）。
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
from pydantic import SecretStr
from sqlalchemy import select

from aegis.api.auth import issue_token
from aegis.api.chat import _relay
from aegis.api.main import create_app
from aegis.apps.support.service import ChatFrame
from aegis.core.config import Settings
from aegis.core.tenancy import Role
from aegis.gateway.schema import LLMRequest
from aegis.obs.metrics import REGISTRY
from aegis.runtime.events import EventType
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.store import EventRecord, EventWriter, SessionRecord

SECRET = "metrics-endpoint-secret-0123456789abcd"  # ≥32B

_FAMILIES = (
    "aegis_http_requests",
    "aegis_chat_first_token_seconds",
    "aegis_chat_request_seconds",
    "aegis_runs_terminated",
    "aegis_llm_tokens",
    "aegis_llm_cost_yuan",
    "aegis_tool_invocations",
    "aegis_handoffs",
    "aegis_cache_requests",
    "aegis_tenant_budget_used_ratio",
    "aegis_documents",
)


class _NullGateway:
    def complete(self, req: LLMRequest):  # pragma: no cover
        raise AssertionError("metrics 面绝不调用 LLM")


class _Limiter:
    async def try_take(self, scope, rate, capacity, cost=1.0):
        return (True, 0.0)


def _make_app(factory, lookup=None):
    gw = _NullGateway()
    return create_app(
        Settings(jwt_secret=SecretStr(SECRET)),
        session_factory=factory,
        runtime=AgentRuntime(gw, factory),
        limiter=_Limiter(),
        gateway=gw,
        approvals_lookup=lookup if lookup is not None else factory,
    )


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _sample(name: str, labels: dict[str, str]) -> float | None:
    return REGISTRY.get_sample_value(name, labels)


async def test_metrics_exposition_contains_all_families(db_session_factory) -> None:
    """GET /metrics：11 族全部出现在 exposition 文本（族在=声明面完整，值另测）。"""
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    for family in _FAMILIES:
        assert family in resp.text, f"缺指标族 {family}"


async def test_scrape_is_readonly(db_session_factory) -> None:
    """scrape 全程只读：刷新+导出不产生任何行（events 行数为证）。"""
    tid, sid = f"t-me-{uuid4().hex[:8]}", f"me-{uuid4().hex[:8]}"
    async with db_session_factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=sid, tenant_id=tid, user_id="u-me"))
    w = await EventWriter.open(db_session_factory, sid, "run-me-1")
    await w.append(EventType.USER_MESSAGE, {"content": "hi"})

    async def _count() -> int:
        async with db_session_factory() as s:
            return len((await s.execute(select(EventRecord.id).where(EventRecord.session_id == sid))).all())

    before = await _count()
    async with _client(_make_app(db_session_factory)) as c:
        await c.get("/metrics")
    assert await _count() == before == 1


async def test_scrape_survives_db_down(db_session_factory) -> None:
    """fail-safe 端到端：维护面工厂全炸，/metrics 仍 200（族跳过留上次值，绝不 500）。"""

    class _Broken:
        def __call__(self):
            raise RuntimeError("db down")

    async with _client(_make_app(db_session_factory, lookup=_Broken())) as c:
        resp = await c.get("/metrics")
    assert resp.status_code == 200


async def test_http_counter_uses_route_template_not_raw_path(db_session_factory) -> None:
    """中间件：path label=路由模板（防基数爆炸）；未匹配路由归并 unmatched。"""
    app = _make_app(db_session_factory)
    tmpl = {"path": "/v1/sessions/{session_id}/events", "method": "GET", "status": "404"}
    health = {"path": "/healthz", "method": "GET", "status": "200"}
    unmatched = {"path": "unmatched", "method": "GET", "status": "404"}
    t0 = {
        k: _sample("aegis_http_requests_total", v) or 0.0
        for k, v in {"tmpl": tmpl, "health": health, "unmatched": unmatched}.items()
    }
    token = issue_token(user_id="op-me", tenant_id="t-me", role=Role.OPERATOR, ttl_s=600, secret=SECRET)
    async with _client(app) as c:
        await c.get("/healthz")
        await c.get("/healthz")
        await c.get(f"/v1/sessions/me-ghost-{uuid4().hex[:6]}/events", headers={"Authorization": f"Bearer {token}"})
        await c.get("/no/such/route")
    assert (_sample("aegis_http_requests_total", health) or 0.0) - t0["health"] == 2
    assert (_sample("aegis_http_requests_total", tmpl) or 0.0) - t0["tmpl"] == 1  # 模板而非真实 id 路径
    assert (_sample("aegis_http_requests_total", unmatched) or 0.0) - t0["unmatched"] == 1


async def _frames(items: list[ChatFrame]) -> AsyncIterator[ChatFrame]:
    for item in items:
        yield item


async def test_relay_observes_first_token_and_duration(db_session_factory) -> None:
    """chat 打点：首个 token 帧恰记一次首 token；流尽恰记一次全程（样本计数断言）。"""
    tid = f"t-rl-{uuid4().hex[:8]}"
    first = ChatFrame("token", {"text": "你"})
    rest = [ChatFrame("token", {"text": "好"}), ChatFrame("done", {"usage": {}})]
    chunks = [c async for c in _relay(first, _frames(rest), t0=time.monotonic(), tenant_id=tid)]
    assert len(chunks) == 3
    assert _sample("aegis_chat_first_token_seconds_count", {"tenant_id": tid}) == 1
    assert _sample("aegis_chat_request_seconds_count", {"tenant_id": tid}) == 1


async def test_relay_without_token_frames_skips_first_token(db_session_factory) -> None:
    """无 token 帧的流（如 handoff 直通）：不虚报首 token，全程照记。"""
    tid = f"t-rl-{uuid4().hex[:8]}"
    first = ChatFrame("handoff", {"ticket_id": "tk-1"})
    rest = [ChatFrame("done", {"usage": {}})]
    _ = [c async for c in _relay(first, _frames(rest), t0=time.monotonic(), tenant_id=tid)]
    assert _sample("aegis_chat_first_token_seconds_count", {"tenant_id": tid}) is None
    assert _sample("aegis_chat_request_seconds_count", {"tenant_id": tid}) == 1

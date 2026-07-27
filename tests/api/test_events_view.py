"""M3.10 交付③：GET /v1/sessions/{id}/events（U14）——staff 面矩阵/审计留痕/原文 JSON。

M4.1 trace API 的底座：本步只出原文（masker 归 M4.1）；operator 限本租户（403 点名
越界=staff 面口径，与用户面 404 不泄露存在性相对——题 142 分野）；每次访问写
结构化审计日志（02 §7.3"仅 operator+ 可访问且留审计"的最小落地）。
"""

from __future__ import annotations

import logging
from uuid import uuid4

import httpx
from pydantic import SecretStr

from aegis.api.auth import issue_token
from aegis.api.main import create_app
from aegis.core.config import Settings
from aegis.core.tenancy import Role
from aegis.gateway.schema import LLMRequest
from aegis.runtime.events import EventType
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.store import EventWriter, SessionRecord

SECRET = "events-view-secret-0123456789abcdefgh"  # ≥32B


class _NullGateway:
    def complete(self, req: LLMRequest):  # pragma: no cover
        raise AssertionError("events 端点绝不调用 LLM")


class _Limiter:
    async def try_take(self, scope, rate, capacity, cost=1.0):
        return (True, 0.0)


def _make_app(factory):
    gw = _NullGateway()
    return create_app(
        Settings(jwt_secret=SecretStr(SECRET)),
        session_factory=factory,
        runtime=AgentRuntime(gw, factory),
        limiter=_Limiter(),
        gateway=gw,
        approvals_lookup=factory,
    )


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _bearer(tid: str, uid: str, role: Role) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(user_id=uid, tenant_id=tid, role=role, ttl_s=3600, secret=SECRET)}"}


async def _seed(factory, tid: str, sid: str) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=sid, tenant_id=tid, user_id="u-ev1"))
    writer = await EventWriter.open(factory, sid, "run-ev-1")
    await writer.append(EventType.USER_MESSAGE, {"content": "查订单"})
    await writer.append(EventType.ASSISTANT_MESSAGE, {"content": "已发货。"})


async def test_operator_reads_own_tenant_events(db_session_factory) -> None:
    """operator 本租户：原文 JSON（seq/type/payload/run_id 全量——M4.1 底座形态）。"""
    tid, sid = f"t-ev-{uuid4().hex[:8]}", f"ev-{uuid4().hex[:8]}"
    await _seed(db_session_factory, tid, sid)
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.get(f"/v1/sessions/{sid}/events", headers=_bearer(tid, "op-1", Role.OPERATOR))
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == sid
    assert [e["type"] for e in body["events"]] == ["user_message", "assistant_message"]
    assert body["events"][0]["payload"] == {"content": "查订单"}
    assert body["events"][0]["seq"] == 1


async def test_operator_cross_tenant_403(db_session_factory) -> None:
    """staff 面越界显式 403（与用户面 404 不泄露存在性相对——两种威胁模型两种答案）。"""
    tid, sid = f"t-ev-{uuid4().hex[:8]}", f"ev-{uuid4().hex[:8]}"
    await _seed(db_session_factory, tid, sid)
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.get(f"/v1/sessions/{sid}/events", headers=_bearer("t-ev-other", "op-x", Role.OPERATOR))
    assert resp.status_code == 403


async def test_admin_cross_tenant_allowed(db_session_factory) -> None:
    tid, sid = f"t-ev-{uuid4().hex[:8]}", f"ev-{uuid4().hex[:8]}"
    await _seed(db_session_factory, tid, sid)
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.get(f"/v1/sessions/{sid}/events", headers=_bearer("t-ev-hq", "adm-1", Role.ADMIN))
    assert resp.status_code == 200


async def test_user_role_403_and_unknown_404(db_session_factory) -> None:
    """矩阵：终端用户 ❌（trace 含 system prompt/内部工具名——§7 陷阱 12）；查无 404。"""
    tid, sid = f"t-ev-{uuid4().hex[:8]}", f"ev-{uuid4().hex[:8]}"
    await _seed(db_session_factory, tid, sid)
    async with _client(_make_app(db_session_factory)) as c:
        user = await c.get(f"/v1/sessions/{sid}/events", headers=_bearer(tid, "u-ev1", Role.USER))
        ghost = await c.get(
            f"/v1/sessions/ev-ghost-{uuid4().hex[:6]}/events", headers=_bearer(tid, "op-1", Role.OPERATOR)
        )
    assert user.status_code == 403
    assert ghost.status_code == 404


async def test_access_writes_audit_log(db_session_factory, caplog) -> None:
    """02 §7.3 审计最小落地：每次访问一行结构化留痕（谁/什么角色/看了哪个会话）。"""
    tid, sid = f"t-ev-{uuid4().hex[:8]}", f"ev-{uuid4().hex[:8]}"
    await _seed(db_session_factory, tid, sid)
    with caplog.at_level(logging.INFO, logger="aegis.api.events_view"):
        async with _client(_make_app(db_session_factory)) as c:
            await c.get(f"/v1/sessions/{sid}/events", headers=_bearer(tid, "op-1", Role.OPERATOR))
    line = next(r.message for r in caplog.records if "trace 访问" in r.message)
    assert "op-1" in line and sid in line and "operator" in line

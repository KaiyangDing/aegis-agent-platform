"""M3.10 交付③ 建骨架 → M4.1 交付②：GET /v1/sessions/{id}/events = 完整 trace 视图。

staff 面矩阵不变（operator 越界 403 点名 vs 用户面 404 不泄露存在性——题 142 分野）；
响应升级 TraceView（按 run 分组/耗时/用量聚合）+ payload 一律过展示层 masker
（02 §7.3"events 存原文、脱敏在展示层"在端点兑现）；审计留痕不变。
after_seq/limit 已随拍板⑤退役（全仓无生产消费方，分页/增量导出 v2）。
RLS 在场世界的 admin 跨租证人不在本文件（owner 夹具无 RLS）——见 test_rls.py M4.1 增量节。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import uuid4

import httpx
from pydantic import SecretStr

from aegis.api.auth import issue_token
from aegis.api.main import create_app
from aegis.core.config import Settings
from aegis.core.tenancy import Role
from aegis.gateway.metering import UsageRecord
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


async def _seed_row(factory, tid: str, sid: str) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=sid, tenant_id=tid, user_id="u-ev1"))


async def _seed(factory, tid: str, sid: str) -> None:
    await _seed_row(factory, tid, sid)
    writer = await EventWriter.open(factory, sid, "run-ev-1")
    await writer.append(EventType.USER_MESSAGE, {"content": "查订单"})
    await writer.append(EventType.ASSISTANT_MESSAGE, {"content": "已发货。"})


async def test_operator_reads_own_tenant_trace(db_session_factory) -> None:
    """operator 本租户：TraceView 全量——X5 等式/分组/seq/payload/usage 结构齐备。"""
    tid, sid = f"t-ev-{uuid4().hex[:8]}", f"ev-{uuid4().hex[:8]}"
    await _seed(db_session_factory, tid, sid)
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.get(f"/v1/sessions/{sid}/events", headers=_bearer(tid, "op-1", Role.OPERATOR))
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace_id"] == sid  # X5：trace_id ≡ session_id
    assert body["session_id"] == sid
    assert body["tenant_id"] == tid
    assert body["run_state"] == "idle"
    (run,) = body["runs"]
    assert run["run_id"] == "run-ev-1"
    assert run["termination_reason"] is None
    assert [e["type"] for e in run["events"]] == ["user_message", "assistant_message"]
    assert run["events"][0]["payload"] == {"content": "查订单"}
    assert run["events"][0]["seq"] == 1
    assert body["usage"]["requests"] == 0  # 无账本行=零用量结构在场，不是缺字段
    assert isinstance(body["usage"]["cost"], str)  # 钱不过 float（M3.1 契约延伸线上）


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
    assert resp.json()["tenant_id"] == tid


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


async def test_response_payload_masked_with_rule_name(db_session_factory) -> None:
    """出口打码在端点兑现：响应无裸 PII，掩码带规则名（02 §7.3；原文仍在库由 obs 测试钉）。"""
    tid, sid = f"t-ev-{uuid4().hex[:8]}", f"ev-{uuid4().hex[:8]}"
    await _seed_row(db_session_factory, tid, sid)
    writer = await EventWriter.open(db_session_factory, sid, "run-ev-1")
    await writer.append(EventType.ASSISTANT_MESSAGE, {"content": "已登记手机号 13812345678，稍后回复。"})
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.get(f"/v1/sessions/{sid}/events", headers=_bearer(tid, "op-1", Role.OPERATOR))
    content = resp.json()["runs"][0]["events"][0]["payload"]["content"]
    assert "***phone_cn***" in content
    assert "13812345678" not in content


async def test_tool_duration_and_usage_in_response(db_session_factory) -> None:
    """00 §8.2 第一条的端点面：还原每步耗时（tool 实测值）与会话用量（账本聚合）。"""
    tid, sid = f"t-ev-{uuid4().hex[:8]}", f"ev-{uuid4().hex[:8]}"
    await _seed_row(db_session_factory, tid, sid)
    writer = await EventWriter.open(db_session_factory, sid, "run-ev-1")
    call = await writer.append(EventType.TOOL_CALL, {"tool_name": "order_query", "args": {"order_id": "AZ-1001"}})
    await writer.append(EventType.TOOL_RESULT, {"tool_call_id": call.id, "result": {"ok": True}, "latency_ms": 42})
    async with db_session_factory() as s:
        async with s.begin():
            s.add(
                UsageRecord(
                    request_id=f"rq-ev-{uuid4().hex[:6]}",
                    tenant_id=tid,
                    session_id=sid,
                    tier="standard",
                    provider="bailian",
                    model="m-a",
                    prompt_tokens=100,
                    completion_tokens=50,
                    cached=False,
                    cost=Decimal("0.002000"),
                )
            )
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.get(f"/v1/sessions/{sid}/events", headers=_bearer(tid, "op-1", Role.OPERATOR))
    body = resp.json()
    events = body["runs"][0]["events"]
    assert events[0]["duration_ms"] is None  # tool_call 本身不配耗时
    assert events[1]["duration_ms"] == 42
    assert body["usage"]["requests"] == 1
    assert body["usage"]["prompt_tokens"] == 100
    assert Decimal(body["usage"]["cost"]) == Decimal("0.002")

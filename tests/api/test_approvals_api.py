"""M3.9 交付②：POST /v1/approvals/{approval_id}——对抗④矩阵/decide CAS 透出/恢复入口触发。

恢复入口用 _SpyRuntime（继承 AgentRuntime 覆写 resume）：§4.9 测试蓝图点名
"恢复入口被调【假恢复 spy】"——审批→执行→续跑的真实语义已由 tests/runtime/
test_suspend_resume.py 钉死，本文件只钉端点编排契约：授权序（401/403/404）、
decide CAS 结果原样透出（409）、resume 实参、JSON 摘要形状。
授权查读缝 approvals_lookup 注入同一 SAVEPOINT 工厂（测试连接无 RLS，
owner 视角与 app 视角同貌——RLS 下两工厂的分工由生产装配承担）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from pydantic import SecretStr
from sqlalchemy import select

from aegis.api.auth import issue_token
from aegis.api.main import create_app
from aegis.core.config import Settings
from aegis.core.tenancy import Role
from aegis.gateway.schema import StopChunk, TextDelta, UsageChunk
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import TerminationReason
from aegis.runtime.store import ApprovalRecord, ApprovalStatus, RunState, SessionRecord

SECRET = "approvals-test-secret-0123456789abcd"  # ≥32B（RFC 7518 下限）


class _EchoGateway:
    """GatewayLike 最小桩：本文件不走 chat，网关只为 create_app 组装 ChatService 存在。"""

    async def complete(self, req):
        yield TextDelta(text="好的。")
        yield UsageChunk(model="stub", prompt_tokens=1, completion_tokens=1)
        yield StopChunk(reason="end_turn")


class _Limiter:
    async def try_take(self, scope, rate, capacity, cost=1.0):
        return (True, 0.0)


class _SpyRuntime(AgentRuntime):
    """覆写 resume 的间谍：记录实参、按剧本吐事件——恢复语义不在本文件重测。"""

    def __init__(self, gw, factory) -> None:
        super().__init__(gw, factory)
        self.calls: list[tuple[str, str | None]] = []
        self.script: list[AgentEvent] = []

    async def resume(self, spec, session_id, approval_id=None, *, text_sink=None):
        # text_sink：基类 M3.10① 增的 keyword 缝——覆写必须收下（Liskov/mypy [override]），
        # 审批端点是同步 JSON 消费者不传 sink，此处不使用
        self.calls.append((session_id, approval_id))
        for event in self.script:
            yield event


def _make_app(factory, spy: _SpyRuntime):
    return create_app(
        Settings(jwt_secret=SecretStr(SECRET)),
        session_factory=factory,
        runtime=spy,
        limiter=_Limiter(),
        gateway=_EchoGateway(),
        approvals_lookup=factory,
    )


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _bearer(role: Role = Role.OPERATOR, uid: str = "op-a1", tid: str = "tenant-a") -> dict[str, str]:
    token = issue_token(user_id=uid, tenant_id=tid, role=role, ttl_s=3600, secret=SECRET)
    return {"Authorization": f"Bearer {token}"}


async def _seed(
    factory,
    sid: str,
    *,
    tenant: str = "tenant-a",
    status: str = ApprovalStatus.PENDING.value,
    expires_delta: timedelta = timedelta(hours=1),
) -> str:
    """挂起态夹具：awaiting 会话行 + 审批单（test_admission._seed_awaiting 同款）。"""
    aid = f"ap-{sid}"
    async with factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=sid, tenant_id=tenant, user_id="u-a1", run_state=RunState.AWAITING_APPROVAL.value))
            s.add(
                ApprovalRecord(
                    id=aid,
                    session_id=sid,
                    tenant_id=tenant,
                    tool_name="refund_apply",
                    args={"order_id": "1024", "amount": 300},
                    status=status,
                    expires_at=datetime.now(UTC) + expires_delta,
                )
            )
    return aid


def _terminated_script(sid: str) -> list[AgentEvent]:
    return [
        AgentEvent(
            id="ev-spy-1",
            session_id=sid,
            run_id="r-spy",
            seq=1,
            type=EventType.ASSISTANT_MESSAGE,
            payload={"content": "退款已执行"},
        ),
        AgentEvent(
            id="ev-spy-2",
            session_id=sid,
            run_id="r-spy",
            seq=2,
            type=EventType.LOOP_TERMINATED,
            payload={"reason": TerminationReason.COMPLETED.value, "iteration": 1, "detail": ""},
        ),
    ]


async def _approval_row(factory, aid: str) -> ApprovalRecord:
    async with factory() as s:
        return (await s.execute(select(ApprovalRecord).where(ApprovalRecord.id == aid))).scalar_one()


async def test_missing_token_401(db_session_factory) -> None:
    spy = _SpyRuntime(_EchoGateway(), db_session_factory)
    async with _client(_make_app(db_session_factory, spy)) as c:
        assert (await c.post("/v1/approvals/ap-x", json={"decision": "approve"})).status_code == 401


async def test_user_role_403(db_session_factory) -> None:
    """矩阵：终端用户不进审批端点（02 §7.1 该行 user 列 ❌）。"""
    spy = _SpyRuntime(_EchoGateway(), db_session_factory)
    async with _client(_make_app(db_session_factory, spy)) as c:
        resp = await c.post("/v1/approvals/ap-x", json={"decision": "approve"}, headers=_bearer(Role.USER, "u-a1"))
    assert resp.status_code == 403
    assert spy.calls == []


async def test_operator_cross_tenant_403(db_session_factory) -> None:
    """对抗④：租户 A 坐席裁决租户 B 审批单 → 403；单据零翻转、恢复零触发。"""
    aid = await _seed(db_session_factory, "s-adv4", tenant="tenant-b")
    spy = _SpyRuntime(_EchoGateway(), db_session_factory)
    async with _client(_make_app(db_session_factory, spy)) as c:
        resp = await c.post(f"/v1/approvals/{aid}", json={"decision": "approve"}, headers=_bearer())
    assert resp.status_code == 403
    assert (await _approval_row(db_session_factory, aid)).status == ApprovalStatus.PENDING.value
    assert spy.calls == []


async def test_admin_cross_tenant_allowed(db_session_factory) -> None:
    """admin 平台级放行（矩阵 ✅ 无租户限定）：跨租户批准落锤并触发恢复。"""
    aid = await _seed(db_session_factory, "s-admin", tenant="tenant-b")
    spy = _SpyRuntime(_EchoGateway(), db_session_factory)
    spy.script = _terminated_script("s-admin")
    async with _client(_make_app(db_session_factory, spy)) as c:
        resp = await c.post(
            f"/v1/approvals/{aid}", json={"decision": "approve"}, headers=_bearer(Role.ADMIN, "adm-1", "tenant-a")
        )
    assert resp.status_code == 200
    assert (await _approval_row(db_session_factory, aid)).status == ApprovalStatus.APPROVED.value
    assert spy.calls == [("s-admin", aid)]


async def test_unknown_approval_404(db_session_factory) -> None:
    spy = _SpyRuntime(_EchoGateway(), db_session_factory)
    async with _client(_make_app(db_session_factory, spy)) as c:
        resp = await c.post("/v1/approvals/ap-ghost", json={"decision": "approve"}, headers=_bearer())
    assert resp.status_code == 404


async def test_approve_flips_and_resumes(db_session_factory) -> None:
    """主路径：decide CAS 落锤（operator_id 入账）→ resume(approval_id) 恰一次 → done 摘要。"""
    aid = await _seed(db_session_factory, "s-ok")
    spy = _SpyRuntime(_EchoGateway(), db_session_factory)
    spy.script = _terminated_script("s-ok")
    async with _client(_make_app(db_session_factory, spy)) as c:
        resp = await c.post(f"/v1/approvals/{aid}", json={"decision": "approve"}, headers=_bearer())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done" and body["reason"] == "completed"
    assert body["reply"] == "退款已执行"
    assert (body["approval_id"], body["session_id"], body["events"]) == (aid, "s-ok", 2)
    row = await _approval_row(db_session_factory, aid)
    assert (row.status, row.operator_id) == (ApprovalStatus.APPROVED.value, "op-a1")
    assert spy.calls == [("s-ok", aid)]


async def test_reject_flips_and_resumes(db_session_factory) -> None:
    """拒绝同走恢复单入口（M2.9 拒绝族轻量路径在 runtime 侧，端点不区分对待）。"""
    aid = await _seed(db_session_factory, "s-rej")
    spy = _SpyRuntime(_EchoGateway(), db_session_factory)
    async with _client(_make_app(db_session_factory, spy)) as c:
        resp = await c.post(f"/v1/approvals/{aid}", json={"decision": "reject"}, headers=_bearer())
    assert resp.status_code == 200
    assert resp.json()["decision"] == "reject"
    assert (await _approval_row(db_session_factory, aid)).status == ApprovalStatus.REJECTED.value
    assert spy.calls == [("s-rej", aid)]


async def test_expired_approval_409(db_session_factory) -> None:
    """C7 fail-closed 原样透出：过期单 decide False → 409；单据留 pending 归 reaper。"""
    aid = await _seed(db_session_factory, "s-exp", expires_delta=timedelta(hours=-1))
    spy = _SpyRuntime(_EchoGateway(), db_session_factory)
    async with _client(_make_app(db_session_factory, spy)) as c:
        resp = await c.post(f"/v1/approvals/{aid}", json={"decision": "approve"}, headers=_bearer())
    assert resp.status_code == 409
    assert (await _approval_row(db_session_factory, aid)).status == ApprovalStatus.PENDING.value
    assert spy.calls == []


async def test_double_decision_409(db_session_factory) -> None:
    """重复决策：CAS 输家拿 False → 409，绝不覆盖赢家（C11）。"""
    aid = await _seed(db_session_factory, "s-dup", status=ApprovalStatus.APPROVED.value)
    spy = _SpyRuntime(_EchoGateway(), db_session_factory)
    async with _client(_make_app(db_session_factory, spy)) as c:
        resp = await c.post(f"/v1/approvals/{aid}", json={"decision": "reject"}, headers=_bearer())
    assert resp.status_code == 409
    assert spy.calls == []


async def test_bad_decision_422(db_session_factory) -> None:
    spy = _SpyRuntime(_EchoGateway(), db_session_factory)
    async with _client(_make_app(db_session_factory, spy)) as c:
        resp = await c.post("/v1/approvals/ap-x", json={"decision": "maybe"}, headers=_bearer())
    assert resp.status_code == 422


async def test_summary_awaiting_when_resume_hits_new_gate(db_session_factory) -> None:
    """续跑又撞新审批闸（干净挂起零终止事件）→ awaiting_approval 摘要带新单号。"""
    aid = await _seed(db_session_factory, "s-regate")
    spy = _SpyRuntime(_EchoGateway(), db_session_factory)
    spy.script = [
        AgentEvent(
            id="ev-spy-3",
            session_id="s-regate",
            run_id="r-spy",
            seq=1,
            type=EventType.APPROVAL_REQUESTED,
            payload={
                "approval_id": "ap-next",
                "tool_name": "refund_apply",
                "args": {"order_id": "2048", "amount": 500},
                "expires_at": "2026-07-27T00:00:00+00:00",
            },
        ),
    ]
    async with _client(_make_app(db_session_factory, spy)) as c:
        resp = await c.post(f"/v1/approvals/{aid}", json={"decision": "approve"}, headers=_bearer())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "awaiting_approval"
    assert (body["next_approval_id"], body["tool_name"]) == ("ap-next", "refund_apply")

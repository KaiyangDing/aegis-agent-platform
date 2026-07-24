"""M3.2：POST /v1/chat 入站三件——限流 429/互斥 409/准入与显式取消 + user_message 经 run 落盘。

状态码分工不变量全钉：401 认证/403 角色/404 归属/409 冲突/422 载荷/429 限流。
网关用最小文本桩（GatewayLike 形状），锁用可编程假锁——零真实调用零 Redis 依赖；
DB 走 SAVEPOINT 夹具。
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
from aegis.runtime.events import EventType
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.store import ApprovalRecord, ApprovalStatus, EventRecord, RunState, SessionRecord

SECRET = "admission-test-secret-0123456789abcd"  # ≥32B（RFC 7518 下限）


class _EchoGateway:
    """GatewayLike 最小桩：一段文本 + usage + stop（网关顺序不变量以 StopChunk 收尾）。"""

    async def complete(self, req):
        yield TextDelta(text="好的，已收到。")
        yield UsageChunk(model="stub", prompt_tokens=1, completion_tokens=1)
        yield StopChunk(reason="end_turn")


class _Limiter:
    """可编程入站限流桩：记录被问过的 scope（断言租户维度前缀）。"""

    def __init__(self, allow: bool = True, wait: float = 2.0) -> None:
        self.allow = allow
        self.wait = wait
        self.asked: list[str] = []

    async def try_take(self, scope, rate, capacity, cost=1.0):
        self.asked.append(scope)
        return (True, 0.0) if self.allow else (False, self.wait)


class _HeldLock:
    """acquire 恒 False：模拟锁被另一请求持有（hold_session_lock 将抛 SessionLockHeld）。"""

    async def acquire(self, session_id, owner_token, *, ttl_s=30.0):
        return False

    async def extend(self, session_id, owner_token, *, ttl_s=30.0):
        return False

    async def release(self, session_id, owner_token):
        return False


def _make_app(factory, *, lock=None, limiter=None):
    runtime = AgentRuntime(_EchoGateway(), factory, lock=lock)
    return create_app(
        Settings(jwt_secret=SecretStr(SECRET)),
        session_factory=factory,
        runtime=runtime,
        limiter=limiter or _Limiter(),
    )


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _bearer(role: Role = Role.USER, uid: str = "u-a1", tid: str = "tenant-a") -> dict[str, str]:
    token = issue_token(user_id=uid, tenant_id=tid, role=role, ttl_s=3600, secret=SECRET)
    return {"Authorization": f"Bearer {token}"}


def _payload(sid: str = "s-chat-1", msg: str = "你好", cancel: bool = False) -> dict:
    return {"session_id": sid, "message": msg, "cancel_pending_approval": cancel}


async def _events(factory, sid: str) -> list[tuple[int, str]]:
    async with factory() as s:
        rows = (
            await s.execute(
                select(EventRecord.seq, EventRecord.type).where(EventRecord.session_id == sid).order_by(EventRecord.seq)
            )
        ).all()
    return [(r.seq, r.type) for r in rows]


async def _seed_awaiting(factory, sid: str, *, approval_status: str = ApprovalStatus.PENDING.value) -> str:
    """挂起态夹具：awaiting 会话行 + 审批单（默认 pending，未过期）。"""
    aid = f"ap-{sid}"
    async with factory() as s:
        async with s.begin():
            s.add(
                SessionRecord(id=sid, tenant_id="tenant-a", user_id="u-a1", run_state=RunState.AWAITING_APPROVAL.value)
            )
            s.add(
                ApprovalRecord(
                    id=aid,
                    session_id=sid,
                    tenant_id="tenant-a",
                    tool_name="refund_apply",
                    args={"order_id": "1024", "amount": 300},
                    status=approval_status,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
    return aid


async def test_missing_token_401(db_session_factory) -> None:
    async with _client(_make_app(db_session_factory)) as c:
        assert (await c.post("/v1/chat", json=_payload())).status_code == 401


async def test_operator_role_403(db_session_factory) -> None:
    """矩阵：POST /v1/chat 的 operator 列为 —（02 §7.1）——坐席不替用户发消息。"""
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.post("/v1/chat", json=_payload(), headers=_bearer(Role.OPERATOR, "op-a1"))
    assert resp.status_code == 403


async def test_empty_message_422(db_session_factory) -> None:
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.post("/v1/chat", json=_payload(msg=""), headers=_bearer())
    assert resp.status_code == 422


async def test_foreign_session_404(db_session_factory) -> None:
    """#19 归属校验：他人会话回 404 不回 403——不泄露会话存在性。"""
    async with db_session_factory() as s:
        async with s.begin():
            s.add(SessionRecord(id="s-other", tenant_id="tenant-a", user_id="u-a2"))
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.post("/v1/chat", json=_payload(sid="s-other"), headers=_bearer(uid="u-a1"))
    assert resp.status_code == 404


async def test_rate_limited_429_with_retry_after(db_session_factory) -> None:
    limiter = _Limiter(allow=False, wait=2.0)
    async with _client(_make_app(db_session_factory, limiter=limiter)) as c:
        resp = await c.post("/v1/chat", json=_payload(), headers=_bearer())
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "2"
    assert limiter.asked == ["inbound:tenant-a"]  # 租户维度 scope（D6），且限流在角色门之后恰问一次


async def test_lock_held_409(db_session_factory) -> None:
    async with _client(_make_app(db_session_factory, lock=_HeldLock())) as c:
        resp = await c.post("/v1/chat", json=_payload(sid="s-locked"), headers=_bearer())
    assert resp.status_code == 409
    assert "处理中" in resp.json()["detail"]
    assert await _events(db_session_factory, "s-locked") == []  # 锁外零事件


async def test_first_message_creates_session_and_runs(db_session_factory) -> None:
    """首见建行（#19 机制）+ user_message 由 loop 写恰一次 + 占位 JSON 摘要。"""
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.post("/v1/chat", json=_payload(sid="s-new"), headers=_bearer())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done" and body["reason"] == "completed"
    assert body["reply"] == "好的，已收到。"
    events = await _events(db_session_factory, "s-new")
    assert [t for _, t in events] == ["user_message", "llm_call", "llm_result", "assistant_message", "loop_terminated"]
    assert [seq for seq, _ in events] == [1, 2, 3, 4, 5]
    async with db_session_factory() as s:
        row = (await s.execute(select(SessionRecord).where(SessionRecord.id == "s-new"))).scalar_one()
    assert (row.tenant_id, row.user_id, row.run_state) == ("tenant-a", "u-a1", RunState.IDLE.value)


async def test_second_message_seq_continues(db_session_factory) -> None:
    app = _make_app(db_session_factory)
    async with _client(app) as c:
        assert (await c.post("/v1/chat", json=_payload(sid="s-cont"), headers=_bearer())).status_code == 200
        assert (
            await c.post("/v1/chat", json=_payload(sid="s-cont", msg="再问一句"), headers=_bearer())
        ).status_code == 200
    events = await _events(db_session_factory, "s-cont")
    assert [seq for seq, _ in events] == list(range(1, 11))  # 两 run 各 5 事件，seq 跨 run 接续
    assert sum(1 for _, t in events if t == EventType.USER_MESSAGE.value) == 2  # 绝无双写


async def test_awaiting_approval_blocks_new_run(db_session_factory) -> None:
    """准入规则：审批挂起期间新消息不开新循环（02 §2 ③）——零新事件。"""
    aid = await _seed_awaiting(db_session_factory, "s-wait")
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.post("/v1/chat", json=_payload(sid="s-wait", msg="怎么还没好"), headers=_bearer())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "awaiting_approval" and body["approval_id"] == aid
    assert await _events(db_session_factory, "s-wait") == []


async def test_cancel_flips_approval_and_terminates(db_session_factory) -> None:
    """显式取消：审批单 CAS 翻 cancelled → M2.9 终止路径（approval_cancelled + CANCELLED 终止 + 归 idle）。"""
    aid = await _seed_awaiting(db_session_factory, "s-cancel")
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.post("/v1/chat", json=_payload(sid="s-cancel", cancel=True), headers=_bearer())
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    async with db_session_factory() as s:
        approval = (await s.execute(select(ApprovalRecord).where(ApprovalRecord.id == aid))).scalar_one()
        session = (await s.execute(select(SessionRecord).where(SessionRecord.id == "s-cancel"))).scalar_one()
    assert approval.status == ApprovalStatus.CANCELLED.value
    assert session.run_state == RunState.IDLE.value
    assert [t for _, t in await _events(db_session_factory, "s-cancel")] == ["approval_cancelled", "loop_terminated"]


async def test_cancel_already_decided_409(db_session_factory) -> None:
    """取消与坐席批准赛跑输了：CAS False → 409 按当前实况回，不覆盖赢家。"""
    await _seed_awaiting(db_session_factory, "s-raced", approval_status=ApprovalStatus.APPROVED.value)
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.post("/v1/chat", json=_payload(sid="s-raced", cancel=True), headers=_bearer())
    assert resp.status_code == 409


async def test_cancel_without_pending_409(db_session_factory) -> None:
    async with db_session_factory() as s:
        async with s.begin():
            s.add(SessionRecord(id="s-idle", tenant_id="tenant-a", user_id="u-a1"))
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.post("/v1/chat", json=_payload(sid="s-idle", cancel=True), headers=_bearer())
    assert resp.status_code == 409

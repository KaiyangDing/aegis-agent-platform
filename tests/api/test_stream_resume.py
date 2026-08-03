"""M3.10 交付③：GET /v1/sessions/{id}/stream 重订阅通道——回放/续传/归属/活尾/重置帧。

事件用 EventWriter 伪造（_stage_crash 同款手法）；活尾用"未启动的快轮询 notifier"
（degrade 路径=C22 兜底本身，0.05s 节拍让测试确定且快）。id 全部随机（偏差52 铁律）。
"""

from __future__ import annotations

import asyncio
import json
import os
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aegis.api.auth import issue_token
from aegis.api.main import create_app
from aegis.api.notify import EventNotifier
from aegis.apps.support.service import msgbuf_key
from aegis.core.config import Settings
from aegis.core.tenancy import Role
from aegis.gateway.schema import LLMRequest
from aegis.runtime.events import EventType
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.store import EventRecord, EventWriter, MessageRecord, RunState, SessionRecord

SECRET = "stream-test-secret-0123456789abcdefgh"  # ≥32B

TEST_DATABASE_URL = os.environ.get("AEGIS_TEST_DATABASE_URL", "postgresql+asyncpg://aegis:aegis@localhost:5432/aegis")


async def _committed_env():
    """活尾类并发测试的 DB 环境（偏差53）：流式请求与续写任务两个协程并发——
    SAVEPOINT 单连接夹具的栈会被交错操作搞崩（savepoint does not exist），
    必须真提交独立引擎（test_rls 先例）+ finally 过滤式清理。"""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        await engine.dispose()
        if os.environ.get("CI"):
            raise
        pytest.skip("本地 PostgreSQL 未启动")
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _cleanup_session(factory, sid: str) -> None:
    """过滤式清理（M2.10 教训）：只删自家随机 id 的行，绝不全表清。"""
    async with factory() as s:
        async with s.begin():
            await s.execute(delete(EventRecord).where(EventRecord.session_id == sid))
            await s.execute(delete(MessageRecord).where(MessageRecord.session_id == sid))
            await s.execute(delete(SessionRecord).where(SessionRecord.id == sid))


class _NullGateway:
    def complete(self, req: LLMRequest):  # pragma: no cover - 流端点不触 LLM
        raise AssertionError("GET 通道绝不调用 LLM")


class _Limiter:
    async def try_take(self, scope, rate, capacity, cost=1.0):
        return (True, 0.0)


def _fast_notifier() -> EventNotifier:
    """未启动的 notifier=降级轮询路径（C22 兜底）；0.05s 节拍让活尾测试确定且快。"""
    return EventNotifier("postgresql+asyncpg://unused/unused", poll_interval_s=0.05)


def _make_app(factory, *, msg_redis=None):
    gw = _NullGateway()
    return create_app(
        Settings(jwt_secret=SecretStr(SECRET)),
        session_factory=factory,
        runtime=AgentRuntime(gw, factory),
        limiter=_Limiter(),
        gateway=gw,
        approvals_lookup=factory,
        notifier=_fast_notifier(),
        msg_redis=msg_redis,
    )


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _bearer(tid: str, uid: str, role: Role = Role.USER) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(user_id=uid, tenant_id=tid, role=role, ttl_s=3600, secret=SECRET)}"}


def _frames(text: str) -> list[tuple[str, dict, int | None]]:
    out: list[tuple[str, dict, int | None]] = []
    for block in text.strip().split("\n\n"):
        event, data, seq = "", {}, None
        for line in block.split("\n"):
            if line.startswith("id: "):
                seq = int(line[4:])
            elif line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        out.append((event, data, seq))
    return out


async def _seed_finished_run(factory, tid: str, sid: str) -> None:
    """已完结 run 的事件流：user→llm_call→llm_result(ok,usage)→assistant→terminated；idle。"""
    async with factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=sid, tenant_id=tid, user_id="u-st1"))
    writer = await EventWriter.open(factory, sid, "run-replay-1")
    await writer.append(EventType.USER_MESSAGE, {"content": "查订单"})
    await writer.append(EventType.LLM_CALL, {"iteration": 1, "tier": "standard", "input_tokens_est": 10})
    await writer.append(
        EventType.LLM_RESULT,
        {
            "iteration": 1,
            "status": "ok",
            "text": "订单已发货。",
            "tool_calls": [],
            "stop_reason": "end_turn",
            "model": "stub",
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            "cached": False,
            "output_tokens_est": 7,
            "latency_ms": 3,
        },
    )
    await writer.append(EventType.ASSISTANT_MESSAGE, {"content": "订单已发货。", "token_usage": 7})
    await writer.append(EventType.LOOP_TERMINATED, {"reason": "completed", "iteration": 1, "detail": "stub"})


async def test_replay_translates_events_with_seq_ids(db_session_factory) -> None:
    """回放：assistant→token(带 id:=seq)、terminated→done(usage 从 llm_result 累计)；idle 即关流。"""
    tid, sid = f"t-st-{uuid4().hex[:8]}", f"st-{uuid4().hex[:8]}"
    await _seed_finished_run(db_session_factory, tid, sid)
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.get(f"/v1/sessions/{sid}/stream", headers=_bearer(tid, "u-st1"))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    frames = _frames(resp.text)
    # (73) 修复后 user_message(seq=1) 也译——重放不再是半边对话
    assert [(k, seq) for k, _, seq in frames] == [("user_message", 1), ("token", 4), ("done", 5)]
    assert frames[0][1]["text"] == "查订单"
    assert frames[1][1]["text"] == "订单已发货。"
    assert frames[2][1]["reason"] == "completed"
    assert frames[2][1]["usage"] == {"prompt_tokens": 11, "completion_tokens": 7}


async def test_after_seq_and_last_event_id_take_max(db_session_factory) -> None:
    """续传双源取 max：Last-Event-ID=4 优先于 query 0——重复帧零发送（EventSource 重连语义）。"""
    tid, sid = f"t-st-{uuid4().hex[:8]}", f"st-{uuid4().hex[:8]}"
    await _seed_finished_run(db_session_factory, tid, sid)
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.get(
            f"/v1/sessions/{sid}/stream?after_seq=0",
            headers={**_bearer(tid, "u-st1"), "Last-Event-ID": "4"},
        )
    frames = _frames(resp.text)
    assert [(k, seq) for k, _, seq in frames] == [("done", 5)]


async def test_foreign_session_is_404(db_session_factory) -> None:
    """#19 归属：他人会话 404 不泄露存在性（用户级）；矩阵 operator 列 — → 403。"""
    tid, sid = f"t-st-{uuid4().hex[:8]}", f"st-{uuid4().hex[:8]}"
    await _seed_finished_run(db_session_factory, tid, sid)
    async with _client(_make_app(db_session_factory)) as c:
        other = await c.get(f"/v1/sessions/{sid}/stream", headers=_bearer(tid, "u-other"))
        op = await c.get(f"/v1/sessions/{sid}/stream", headers=_bearer(tid, "op-1", Role.OPERATOR))
    assert other.status_code == 404
    assert op.status_code == 403


async def test_message_reset_emitted_before_live_tail(r) -> None:
    """重连整条重推（ADR-007/D11）：进行中会话重连——回放（无帧）→ message_reset(整条现状)
    → 活尾推达续内容与终止。并发双协程走真提交独立引擎（偏差53）。"""
    engine, factory = await _committed_env()
    tid, sid = f"t-st-{uuid4().hex[:8]}", f"st-{uuid4().hex[:8]}"
    try:
        async with factory() as s:
            async with s.begin():
                s.add(SessionRecord(id=sid, tenant_id=tid, user_id="u-st1", run_state=RunState.RUNNING.value))
        writer = await EventWriter.open(factory, sid, "run-reset-1")
        await writer.append(EventType.USER_MESSAGE, {"content": "讲个长故事"})
        await r.set(msgbuf_key(sid), "从前有座山，山里", ex=60)

        async def _finish_run() -> None:
            await asyncio.sleep(0.15)
            w2 = await EventWriter.open(factory, sid, "run-reset-1b")
            await w2.append(EventType.ASSISTANT_MESSAGE, {"content": "从前有座山，山里有座庙。"})
            await w2.append(EventType.LOOP_TERMINATED, {"reason": "completed", "iteration": 1, "detail": "stub"})

        async with _client(_make_app(factory, msg_redis=r)) as c:
            task = asyncio.create_task(_finish_run())
            resp = await c.get(f"/v1/sessions/{sid}/stream", headers=_bearer(tid, "u-st1"))
            await task
        frames = _frames(resp.text)
        kinds = [k for k, _, _ in frames]
        # (73) 修复后：回放含用户侧气泡 → msgbuf 整条重置 → 活尾终稿与终止
        assert kinds == ["user_message", "message_reset", "token", "done"]
        assert frames[0][1]["text"] == "讲个长故事"
        assert frames[1][1]["text"] == "从前有座山，山里"
        assert frames[2][1]["text"] == "从前有座山，山里有座庙。"
    finally:
        await _cleanup_session(factory, sid)
        await engine.dispose()


async def test_live_tail_streams_new_events_until_terminated() -> None:
    """活尾（审批后续跑的统一入口）：awaiting 会话保持在流，新事件到达即推帧、终止即关流。
    并发双协程走真提交独立引擎（偏差53：SAVEPOINT 单连接夹具不支持并发）。"""
    engine, factory = await _committed_env()
    tid, sid = f"t-st-{uuid4().hex[:8]}", f"st-{uuid4().hex[:8]}"
    try:
        async with factory() as s:
            async with s.begin():
                s.add(SessionRecord(id=sid, tenant_id=tid, user_id="u-st1", run_state=RunState.AWAITING_APPROVAL.value))
        writer = await EventWriter.open(factory, sid, "run-live-1")
        await writer.append(EventType.USER_MESSAGE, {"content": "退款"})

        async def _later_continuation() -> None:
            await asyncio.sleep(0.15)
            w2 = await EventWriter.open(factory, sid, "run-live-2")
            await w2.append(EventType.ASSISTANT_MESSAGE, {"content": "退款已提交。"})
            await w2.append(EventType.LOOP_TERMINATED, {"reason": "completed", "iteration": 1, "detail": "续跑"})

        async with _client(_make_app(factory)) as c:
            task = asyncio.create_task(_later_continuation())
            resp = await c.get(f"/v1/sessions/{sid}/stream", headers=_bearer(tid, "u-st1"))
            await task
        frames = _frames(resp.text)
        kinds = [k for k, _, _ in frames]
        assert kinds[-2:] == ["token", "done"]  # 续跑回复与终止经活尾推达
        assert next(d for k, d, _ in frames if k == "token")["text"] == "退款已提交。"
    finally:
        await _cleanup_session(factory, sid)
        await engine.dispose()


async def test_replay_batching_drains_backlog_before_close(db_session_factory, monkeypatch) -> None:
    """(74)（M4.2③）：首批回放有界（_REPLAY_BATCH 分批）——存量排空才进关流判据；
    终止事件落在末批也不早退，可译帧一条不少（silent cap 纪律：分批≠截断）。"""
    from aegis.api import stream as stream_mod

    monkeypatch.setattr(stream_mod, "_REPLAY_BATCH", 2)
    tid, sid = f"t-st-{uuid4().hex[:8]}", f"st-{uuid4().hex[:8]}"
    async with db_session_factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=sid, tenant_id=tid, user_id="u-st1"))  # run_state 缺省 idle
    w = await EventWriter.open(db_session_factory, sid, "run-st-1")
    await w.append(EventType.USER_MESSAGE, {"content": "查订单"})
    await w.append(EventType.ASSISTANT_MESSAGE, {"content": "第一段。"})
    await w.append(EventType.USER_MESSAGE, {"content": "再查"})
    await w.append(EventType.ASSISTANT_MESSAGE, {"content": "第二段。"})
    await w.append(EventType.LOOP_TERMINATED, {"reason": "completed", "iteration": 1, "detail": ""})
    async with _client(_make_app(db_session_factory)) as c:
        resp = await c.get(f"/v1/sessions/{sid}/stream", headers=_bearer(tid, "u-st1"))
    assert resp.status_code == 200
    ids = [ln.split(":", 1)[1].strip() for ln in resp.text.splitlines() if ln.startswith("id:")]
    # 5 事件跨三批（2+2+1）：(73) 修复后 user_message 也译——五帧 seq 1–5 一条不少且有序
    assert ids == ["1", "2", "3", "4", "5"]

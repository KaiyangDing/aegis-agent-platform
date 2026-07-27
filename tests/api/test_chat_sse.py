"""M3.10 交付②：POST /v1/chat SSE 化 + service 流式面（msgbuf/守卫/挂起/错误帧）。

分层测法：HTTP 面走 create_app+ASGITransport（帧序/状态码分工/媒体类型）；
msgbuf 与直答守卫走 ChatService 直测（门控网关制造确定性中间态——SET 先于帧
入队，消费到帧即缓冲可见，无竞态）。零真实调用；Redis 用 db9 夹具 `r`。
id 全部随机（偏差52）：本地库有 seed_demo 的真实 tenant-a 行，固定 id 必撞
tenants_pkey——SAVEPOINT 只回滚自家写入、藏不住已提交残留（M2.10/M3.5(28) 教训）。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from pydantic import SecretStr
from sqlalchemy import select

from aegis.api.auth import issue_token
from aegis.api.main import create_app
from aegis.apps.support.service import ChatService, msgbuf_key
from aegis.core.config import Settings
from aegis.core.tenancy import Role, TenantDirectory, TenantRecord
from aegis.gateway.schema import (
    LLMChunk,
    LLMRequest,
    StopChunk,
    TextDelta,
    ToolCall,
    ToolCallChunk,
    UsageChunk,
)
from aegis.runtime.events import EventType
from aegis.runtime.guardrails import SAFE_REPLY
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.store import (
    ApprovalRecord,
    ApprovalStatus,
    EventRecord,
    EventStoreUnavailable,
    RunState,
    SessionRecord,
)

SECRET = "chat-sse-test-secret-0123456789abcdef"  # ≥32B


def _sid() -> str:
    return f"sse-{uuid4().hex[:10]}"


def _tid() -> str:
    return f"t-sse-{uuid4().hex[:10]}"


def _frames(text: str) -> list[tuple[str, dict]]:
    """SSE 文本 → [(event, data)]：按空行分帧、按前缀取行（线格式契约的消费端镜像）。"""
    out: list[tuple[str, dict]] = []
    for block in text.strip().split("\n\n"):
        event, data = "", {}
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        out.append((event, data))
    return out


class _ChunkSeqGateway:
    """按调用序回放 chunk 级剧本（第 1 次=classify，其后=主循环/直答）。"""

    def __init__(self, scripts: list[list[LLMChunk]]) -> None:
        self._scripts = scripts
        self.calls = 0

    def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        script = self._scripts[min(self.calls, len(self._scripts) - 1)]
        self.calls += 1

        async def _gen() -> AsyncGenerator[LLMChunk]:
            for chunk in script:
                yield chunk

        return _gen()


def _text_script(*texts: str) -> list[LLMChunk]:
    return [
        *[TextDelta(text=t) for t in texts],
        UsageChunk(model="stub", prompt_tokens=1, completion_tokens=1),
        StopChunk(reason="end_turn"),
    ]


class _Limiter:
    async def try_take(self, scope, rate, capacity, cost=1.0):
        return (True, 0.0)


def _make_app(factory, gateway, *, lock=None):
    runtime = AgentRuntime(gateway, factory, lock=lock)
    return create_app(
        Settings(jwt_secret=SecretStr(SECRET)),
        session_factory=factory,
        runtime=runtime,
        limiter=_Limiter(),
        gateway=gateway,
        approvals_lookup=factory,
    )


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _bearer(tid: str, uid: str = "u-sse1") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {issue_token(user_id=uid, tenant_id=tid, role=Role.USER, ttl_s=3600, secret=SECRET)}"
    }


async def _seed_tenant(factory, tid: str, *, config: dict) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(TenantRecord(id=tid, name="流式测试租户", config=config, token_budget_monthly=0))


async def _seed_awaiting(factory, tid: str, sid: str, aid: str) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=sid, tenant_id=tid, user_id="u-sse1", run_state=RunState.AWAITING_APPROVAL.value))
            s.add(
                ApprovalRecord(
                    id=aid,
                    session_id=sid,
                    tenant_id=tid,
                    tool_name="refund_apply",
                    args={"order_id": "1", "amount": 300},
                    status=ApprovalStatus.PENDING.value,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )


async def test_chat_streams_token_and_done_with_usage(db_session_factory) -> None:
    """主分支 SSE：token→done；done 带 trace_id≡session_id 与 llm_result 实测 usage 累计（拍板Ⅴ）。"""
    tid, sid = _tid(), _sid()
    gw = _ChunkSeqGateway([_text_script("tool"), _text_script("好的，", "已收到。")])
    async with _client(_make_app(db_session_factory, gw)) as c:
        resp = await c.post(
            "/v1/chat",
            json={"session_id": sid, "message": "你好", "cancel_pending_approval": False},
            headers=_bearer(tid),
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers.get("x-accel-buffering") == "no"
    frames = _frames(resp.text)
    assert [k for k, _ in frames] == ["token", "done"]
    assert frames[0][1]["text"] == "好的，已收到。"
    done = frames[1][1]
    assert done["reason"] == "completed" and done["trace_id"] == sid
    assert done["usage"] == {"prompt_tokens": 1, "completion_tokens": 1}


async def test_awaiting_admission_streams_pending_then_done(db_session_factory) -> None:
    """审批期间准入：approval_pending + done(awaiting_approval) 两帧短流，零新事件。"""
    tid, sid, aid = _tid(), _sid(), f"ap-{uuid4().hex[:10]}"
    await _seed_awaiting(db_session_factory, tid, sid, aid)
    gw = _ChunkSeqGateway([_text_script("tool")])
    async with _client(_make_app(db_session_factory, gw)) as c:
        resp = await c.post(
            "/v1/chat",
            json={"session_id": sid, "message": "好了吗", "cancel_pending_approval": False},
            headers=_bearer(tid),
        )
    assert resp.status_code == 200
    frames = _frames(resp.text)
    assert [k for k, _ in frames] == ["approval_pending", "done"]
    assert frames[0][1]["approval_id"] == aid
    assert frames[1][1]["reason"] == "awaiting_approval"


async def test_suspension_stream_ends_with_approval_pending_without_done(db_session_factory) -> None:
    """挂起：approval_pending 是末帧、无 done（干净挂起信号）——客户端据此换 GET 通道（ADR-007）。"""
    tid, sid = _tid(), _sid()
    await _seed_tenant(db_session_factory, tid, config={"tools": ["refund_apply"], "approval_threshold": 200})
    call = ToolCall(id="c-1", name="refund_apply", arguments_json='{"order_id": "A-9", "amount": 300}')
    tool_script: list[LLMChunk] = [
        ToolCallChunk(tool_call=call),
        UsageChunk(model="stub", prompt_tokens=1, completion_tokens=1),
        StopChunk(reason="tool_calls"),
    ]
    gw = _ChunkSeqGateway([_text_script("tool"), tool_script])
    async with _client(_make_app(db_session_factory, gw)) as c:
        resp = await c.post(
            "/v1/chat",
            json={"session_id": sid, "message": "退 300 元", "cancel_pending_approval": False},
            headers=_bearer(tid),
        )
    assert resp.status_code == 200
    frames = _frames(resp.text)
    assert frames[-1][0] == "approval_pending"
    assert all(k != "done" for k, _ in frames)
    async with db_session_factory() as s:
        types = (await s.execute(select(EventRecord.type).where(EventRecord.session_id == sid))).scalars().all()
    assert "approval_requested" in types


async def test_cancel_streams_single_done_frame(db_session_factory) -> None:
    """显式取消：done(cancelled) 单帧短流（同端点同媒体类型，协议不分岔）。"""
    tid, sid, aid = _tid(), _sid(), f"ap-{uuid4().hex[:10]}"
    await _seed_awaiting(db_session_factory, tid, sid, aid)
    gw = _ChunkSeqGateway([_text_script("tool")])
    async with _client(_make_app(db_session_factory, gw)) as c:
        resp = await c.post(
            "/v1/chat",
            json={"session_id": sid, "message": "取消", "cancel_pending_approval": True},
            headers=_bearer(tid),
        )
    assert resp.status_code == 200
    frames = _frames(resp.text)
    assert [k for k, _ in frames] == ["done"]
    assert frames[0][1]["reason"] == "cancelled" and frames[0][1]["approval_id"] == aid


async def test_infra_error_after_first_frame_becomes_error_frame(db_session_factory) -> None:
    """已开流无法改状态码：首帧后的基础设施异常译为 error 帧收流（打码话术）。"""

    class _BrokenRuntime(AgentRuntime):
        async def run(self, spec, session_id, user_input, *, text_sink=None):
            async for event in super().run(spec, session_id, user_input, text_sink=text_sink):
                yield event
                if event.type is EventType.ASSISTANT_MESSAGE:
                    raise EventStoreUnavailable("模拟事实源中断")

    tid, sid = _tid(), _sid()
    gw = _ChunkSeqGateway([_text_script("tool"), _text_script("第一句。")])
    runtime = _BrokenRuntime(gw, db_session_factory)
    app = create_app(
        Settings(jwt_secret=SecretStr(SECRET)),
        session_factory=db_session_factory,
        runtime=runtime,
        limiter=_Limiter(),
        gateway=gw,
        approvals_lookup=db_session_factory,
    )
    async with _client(app) as c:
        resp = await c.post(
            "/v1/chat",
            json={"session_id": sid, "message": "你好", "cancel_pending_approval": False},
            headers=_bearer(tid),
        )
    assert resp.status_code == 200
    frames = _frames(resp.text)
    assert frames[-1][0] == "error"
    assert "服务" in frames[-1][1]["message"]  # 打码话术，不透内部异常文本


class _GatedGateway:
    """第二句前卡闸：制造确定性的"进行中"状态（msgbuf 断言无竞态的关键）。"""

    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.calls = 0

    def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        self.calls += 1
        first = self.calls == 1

        async def _gen() -> AsyncGenerator[LLMChunk]:
            if first:
                yield TextDelta(text="tool")
            else:
                yield TextDelta(text="第一句。")
                await self.gate.wait()
                yield TextDelta(text="第二句。")
            yield UsageChunk(model="stub", prompt_tokens=1, completion_tokens=1)
            yield StopChunk(reason="end_turn")

        return _gen()


async def _seed_session(factory, tid: str, sid: str) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(TenantRecord(id=tid, name="流式测试租户", config={"tools": []}, token_budget_monthly=0))
            s.add(SessionRecord(id=sid, tenant_id=tid, user_id="u-sse1"))


async def test_msgbuf_written_during_run_and_cleared_on_done(r, db_session_factory) -> None:
    """进行中消息缓冲（ADR-005 角色1）：段落随流全量覆盖写入、done 时删除。

    时序保证：emit 先写缓冲后入队帧——消费到 token 帧即缓冲必可见（生产侧顺序承诺）。
    """
    tid, sid = _tid(), _sid()
    await _seed_session(db_session_factory, tid, sid)
    gw = _GatedGateway()
    svc = ChatService(
        gateway=gw,
        factory=db_session_factory,
        directory=TenantDirectory(db_session_factory),
        runtime=AgentRuntime(gw, db_session_factory),
        redis=r,
    )
    agen = svc.handle(tenant_id=tid, user_id="u-sse1", session_id=sid, message="慢慢说")
    first = await agen.__anext__()
    assert first.kind == "token" and first.data["text"] == "第一句。"
    assert await r.get(msgbuf_key(sid)) == "第一句。"  # 进行中：缓冲=已生成全文
    gw.gate.set()
    rest = [f async for f in agen]
    assert rest[-1].kind == "done"
    assert await r.get(msgbuf_key(sid)) is None  # done 即删（重连无残影）


async def test_faq_direct_streams_through_output_guard(db_session_factory) -> None:
    """拍板Ⅳ：直答流式段过 OutputGuard——PII 命中截断+SAFE_REPLY，事件与通道两面一致。"""
    tid, sid = _tid(), _sid()
    async with db_session_factory() as s:
        async with s.begin():
            s.add(
                TenantRecord(
                    id=tid,
                    name="流式测试租户",
                    config={"tools": [], "faq": "客服热线 400-800-1234。"},
                    token_budget_monthly=0,
                )
            )
            s.add(SessionRecord(id=sid, tenant_id=tid, user_id="u-sse1"))
    gw = _ChunkSeqGateway([_text_script("faq"), _text_script("好的我来告诉您。", "他的手机号是13800138000。")])
    svc = ChatService(
        gateway=gw,
        factory=db_session_factory,
        directory=TenantDirectory(db_session_factory),
        runtime=AgentRuntime(gw, db_session_factory),
    )
    frames = [f async for f in svc.handle(tenant_id=tid, user_id="u-sse1", session_id=sid, message="怎么联系他")]
    kinds = [f.kind for f in frames]
    assert kinds[-1] == "done" and frames[-1].data["reason"] == "faq_direct"
    joined = "".join(f.data["text"] for f in frames if f.kind == "token")
    assert "13800138000" not in joined  # PII 被截断
    assert joined.endswith(SAFE_REPLY)
    async with db_session_factory() as s:
        rows = (
            await s.execute(
                select(EventRecord.type, EventRecord.payload)
                .where(EventRecord.session_id == sid)
                .order_by(EventRecord.seq)
            )
        ).all()
    types = [row.type for row in rows]
    assert "guardrail_triggered" in types  # 直答通道命中同样留审计
    content = next(row.payload["content"] for row in rows if row.type == "assistant_message")
    assert content == joined  # 通道 ≡ 事件（止损面两面一致）

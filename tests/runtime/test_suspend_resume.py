"""M2.9 交付③：挂起链路 + 恢复单入口 + run_state 状态机 + 闸门 #6 三触发源。

必保路径（00 §6.2）：审批回调（decide CAS）→ 状态翻转 → 单入口恢复。
互斥三重（D17）：decide CAS × 会话锁 × transition CAS——本文件各有正身测试。
LLM 全部走脚本替身（零真实调用）；锁默认无（lock=None 直通），互斥专项注入真 Redis 锁。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Mapping, Sequence
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from aegis.core.locks import RedisSessionLock, SessionLockHeld, new_owner_token
from aegis.gateway.schema import (
    LLMChunk,
    LLMRequest,
    StopChunk,
    TextDelta,
    ToolCall,
    ToolCallChunk,
    UsageChunk,
)
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec
from aegis.runtime.store import (
    ApprovalRecord,
    ApprovalStatus,
    ApprovalStore,
    EventRecord,
    RunState,
    SessionRecord,
    SessionStateStore,
)


def _text_turn(text: str) -> list[LLMChunk]:
    return [
        TextDelta(text=text),
        UsageChunk(model="qwen-plus", prompt_tokens=20, completion_tokens=7),
        StopChunk(reason="end_turn"),
    ]


def _tool_turn(*calls: ToolCall) -> list[LLMChunk]:
    chunks: list[LLMChunk] = [ToolCallChunk(tool_call=c) for c in calls]
    chunks.append(UsageChunk(model="qwen-plus", prompt_tokens=30, completion_tokens=12))
    chunks.append(StopChunk(reason="tool_calls"))
    return chunks


class _ScriptedGateway:
    """按调用序回放脚本并记录请求的替身（无 scoped → 四道直通，本文件不触发辅助调用）。"""

    def __init__(self, scripts: Sequence[Sequence[LLMChunk]]) -> None:
        self.requests: list[LLMRequest] = []
        self._scripts = scripts

    async def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        self.requests.append(req)
        for chunk in self._scripts[len(self.requests) - 1]:
            yield chunk


_REFUND_CALL = ToolCall(id="c-appr", name="demo_refund_apply", arguments_json='{"order_id": "A-9", "amount": 350}')


def _spec(registry) -> AgentSpec:
    return AgentSpec(
        system_prompt="你是演示客服。",
        tools=registry.specs(),
        tenant_config={"approval_threshold": 200},
    )


async def _suspend(
    factory, registry, session_id: str
) -> tuple[AgentRuntime, AgentSpec, _ScriptedGateway, list[AgentEvent]]:
    """驱动一次 run 到挂起（amount=350 > 阈值 200）。gateway 预铺续跑文本轮供 resume 消费。"""
    gateway = _ScriptedGateway([_tool_turn(_REFUND_CALL), _text_turn("退款已提交，请留意到账。")])
    runtime = AgentRuntime(gateway, factory)
    spec = _spec(registry)
    events = [e async for e in runtime.run(spec, session_id, "帮我退 350 元")]
    return runtime, spec, gateway, events


def _approval_id(events: list[AgentEvent]) -> str:
    return next(e for e in events if e.type is EventType.APPROVAL_REQUESTED).payload["approval_id"]


async def _count_events(factory, session_id: str, event_type: EventType) -> int:
    async with factory() as s:
        return (
            await s.execute(
                select(func.count())
                .select_from(EventRecord)
                .where(EventRecord.session_id == session_id, EventRecord.type == event_type.value)
            )
        ).scalar_one()


async def _run_state(factory, session_id: str) -> str:
    async with factory() as s:
        return (await s.execute(select(SessionRecord.run_state).where(SessionRecord.id == session_id))).scalar_one()


async def test_needs_approval_creates_pending_ticket(db_session_factory, make_session, demo_registry) -> None:
    """挂起链路第一件：approvals 行 pending、args 快照是 LLM 原始参数、expires_at 在未来。"""
    await make_session("sr-1")
    _, _, _, events = await _suspend(db_session_factory, demo_registry, "sr-1")
    aid = _approval_id(events)
    async with db_session_factory() as s:
        row = (await s.execute(select(ApprovalRecord).where(ApprovalRecord.id == aid))).scalar_one()
    assert row.status == ApprovalStatus.PENDING.value
    assert row.args == {"order_id": "A-9", "amount": 350}
    assert row.tool_name == "demo_refund_apply"
    assert row.expires_at is not None
    assert row.expires_at > datetime.now(UTC)


async def test_suspend_writes_event_and_flips_state(db_session_factory, make_session, demo_registry) -> None:
    """approval_requested 事件四键落盘；sessions.run_state 翻到 awaiting_approval（T2）。"""
    await make_session("sr-2")
    _, _, _, events = await _suspend(db_session_factory, demo_registry, "sr-2")
    req = next(e for e in events if e.type is EventType.APPROVAL_REQUESTED)
    assert set(req.payload) == {"approval_id", "tool_name", "args", "expires_at"}
    assert req.payload["tool_name"] == "demo_refund_apply"
    assert req.payload["args"] == {"order_id": "A-9", "amount": 350}
    assert isinstance(req.payload["expires_at"], str)  # isoformat 字符串，不是 datetime（坑 9）
    assert await _run_state(db_session_factory, "sr-2") == "awaiting_approval"


async def test_suspend_is_clean_exit_not_termination(r, db_session_factory, make_session, demo_registry) -> None:
    """挂起不是终止（D2）：无 loop_terminated；锁已释放（进程可下线）。"""
    await make_session("sr-3")
    gateway = _ScriptedGateway([_tool_turn(_REFUND_CALL)])
    runtime = AgentRuntime(gateway, db_session_factory, lock=RedisSessionLock(r))
    events = [e async for e in runtime.run(_spec(demo_registry), "sr-3", "帮我退 350 元")]
    assert any(e.type is EventType.APPROVAL_REQUESTED for e in events)
    assert not any(e.type is EventType.LOOP_TERMINATED for e in events)
    assert await r.get("aegis:lock:session:sr-3") is None


async def test_double_decide_single_winner(db_session_factory, make_session, demo_registry) -> None:
    """双坐席同点：decide CAS 赢家恰一个；resume 后 approval_decided 事件恰一条。"""
    await make_session("sr-4")
    runtime, spec, _, events = await _suspend(db_session_factory, demo_registry, "sr-4")
    aid = _approval_id(events)
    approvals = ApprovalStore(db_session_factory)
    assert await approvals.decide(aid, approved=True, operator_id="op-1") is True
    assert await approvals.decide(aid, approved=False, operator_id="op-2") is False
    async for _ in runtime.resume(spec, "sr-4", aid):
        pass
    assert await _count_events(db_session_factory, "sr-4", EventType.APPROVAL_DECIDED) == 1


async def test_resume_approved_executes_and_completes(db_session_factory, make_session, demo_registry) -> None:
    """必保路径全绿：decided(True) → tool_call/tool_result → 续跑至 completed；seq 接续、新 run_id。"""
    await make_session("sr-5")
    runtime, spec, _, s_events = await _suspend(db_session_factory, demo_registry, "sr-5")
    aid = _approval_id(s_events)
    await ApprovalStore(db_session_factory).decide(aid, approved=True, operator_id="op-1")
    r_events = [e async for e in runtime.resume(spec, "sr-5", aid)]
    assert [e.type for e in r_events] == [
        EventType.APPROVAL_DECIDED,
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
        EventType.LLM_CALL,
        EventType.LLM_RESULT,
        EventType.ASSISTANT_MESSAGE,
        EventType.LOOP_TERMINATED,
    ]
    assert r_events[0].payload == {"approval_id": aid, "approved": True, "operator_id": "op-1"}
    assert r_events[0].seq == s_events[-1].seq + 1  # seq 接旧流递增，无空洞
    assert [e.seq for e in r_events] == list(range(r_events[0].seq, r_events[0].seq + len(r_events)))
    assert len({e.run_id for e in r_events}) == 1
    assert r_events[0].run_id != s_events[0].run_id  # 恢复用新 run_id（D16/X5）
    assert r_events[-1].payload["reason"] == "completed"
    assert await _run_state(db_session_factory, "sr-5") == "idle"


async def test_resume_backfills_approval_event_id(db_session_factory, make_session, demo_registry) -> None:
    """审计链闭合（D15/attach_event）：approvals.event_id == 批准执行的 tool_call 事件 id。"""
    await make_session("sr-6")
    runtime, spec, _, s_events = await _suspend(db_session_factory, demo_registry, "sr-6")
    aid = _approval_id(s_events)
    await ApprovalStore(db_session_factory).decide(aid, approved=True, operator_id="op-1")
    r_events = [e async for e in runtime.resume(spec, "sr-6", aid)]
    call_event = next(e for e in r_events if e.type is EventType.TOOL_CALL)
    async with db_session_factory() as s:
        row = (await s.execute(select(ApprovalRecord).where(ApprovalRecord.id == aid))).scalar_one()
    assert row.event_id == call_event.id


async def test_resume_rejected_terminates_cancelled(db_session_factory, make_session, demo_registry) -> None:
    """拒绝：approval_decided(False) → loop_terminated(cancelled)；工具不执行；run_state 归 idle。"""
    await make_session("sr-7")
    runtime, spec, _, s_events = await _suspend(db_session_factory, demo_registry, "sr-7")
    aid = _approval_id(s_events)
    await ApprovalStore(db_session_factory).decide(aid, approved=False, operator_id="op-2")
    r_events = [e async for e in runtime.resume(spec, "sr-7", aid)]
    assert [e.type for e in r_events] == [EventType.APPROVAL_DECIDED, EventType.LOOP_TERMINATED]
    assert r_events[0].payload["approved"] is False
    assert r_events[1].payload["reason"] == "cancelled"
    assert not any(e.type is EventType.TOOL_CALL for e in r_events)
    assert await _run_state(db_session_factory, "sr-7") == "idle"


async def test_cancel_terminates_cancelled(db_session_factory, make_session, demo_registry) -> None:
    """用户撤回：approval_cancelled 事件 + cancelled 终止（闸门 #6 触发源之二）。"""
    await make_session("sr-8")
    runtime, spec, _, s_events = await _suspend(db_session_factory, demo_registry, "sr-8")
    aid = _approval_id(s_events)
    assert await ApprovalStore(db_session_factory).cancel(aid) is True
    r_events = [e async for e in runtime.resume(spec, "sr-8", aid)]
    assert [e.type for e in r_events] == [EventType.APPROVAL_CANCELLED, EventType.LOOP_TERMINATED]
    assert r_events[1].payload["reason"] == "cancelled"


async def test_expired_via_injected_clock_terminates(db_session_factory, make_session, demo_registry) -> None:
    """审批超时（闸门 #6 触发源之三，C7 可注入时钟）：零真实等待翻 expired → cancelled 终止。"""
    await make_session("sr-9")
    runtime, spec, _, s_events = await _suspend(db_session_factory, demo_registry, "sr-9")
    aid = _approval_id(s_events)
    flipped = await ApprovalStore(db_session_factory).expire_due(now=datetime.now(UTC) + timedelta(hours=2))
    assert aid in flipped
    r_events = [e async for e in runtime.resume(spec, "sr-9", aid)]
    assert [e.type for e in r_events] == [EventType.APPROVAL_EXPIRED, EventType.LOOP_TERMINATED]
    assert r_events[1].payload["reason"] == "cancelled"


async def test_resume_pending_raises(db_session_factory, make_session, demo_registry) -> None:
    """未决先恢复 → ValueError（调用顺序防呆 D21：先 decide/cancel/expire 再 resume）。"""
    await make_session("sr-10")
    runtime, spec, _, s_events = await _suspend(db_session_factory, demo_registry, "sr-10")
    aid = _approval_id(s_events)
    with pytest.raises(ValueError, match="pending"):
        async for _ in runtime.resume(spec, "sr-10", aid):
            pass


async def test_concurrent_resume_single_winner(r, db_session_factory, make_session, demo_registry) -> None:
    """并发恢复（真 Redis 锁）：输家 SessionLockHeld 或安静零产出；事件表无重复——三重互斥正身。"""
    await make_session("sr-11")
    runtime, spec, _, s_events = await _suspend(db_session_factory, demo_registry, "sr-11")
    aid = _approval_id(s_events)
    await ApprovalStore(db_session_factory).decide(aid, approved=True, operator_id="op-1")
    rt1 = AgentRuntime(_ScriptedGateway([_text_turn("退款已提交。")]), db_session_factory, lock=RedisSessionLock(r))
    rt2 = AgentRuntime(_ScriptedGateway([_text_turn("退款已提交。")]), db_session_factory, lock=RedisSessionLock(r))

    async def _consume(rt: AgentRuntime) -> object:
        try:
            return [e async for e in rt.resume(spec, "sr-11", aid)]
        except SessionLockHeld:
            return "locked"

    await asyncio.gather(_consume(rt1), _consume(rt2))
    assert await _count_events(db_session_factory, "sr-11", EventType.APPROVAL_DECIDED) == 1
    assert await _count_events(db_session_factory, "sr-11", EventType.LOOP_TERMINATED) == 1
    assert await _count_events(db_session_factory, "sr-11", EventType.TOOL_CALL) == 1  # 批准执行恰一次


async def test_run_while_locked_raises_409_signal(r, db_session_factory, make_session) -> None:
    """锁被占时 run() → SessionLockHeld（M3.2 的 409 语义在运行时层的形状）。"""
    await make_session("sr-12")
    lock = RedisSessionLock(r)
    assert await lock.acquire("sr-12", new_owner_token()) is True
    runtime = AgentRuntime(_ScriptedGateway([]), db_session_factory, lock=lock)
    with pytest.raises(SessionLockHeld):
        async for _ in runtime.run(AgentSpec(system_prompt="你是演示客服。"), "sr-12", "你好"):
            pass


async def test_precheck_veto_feeds_back_without_execution(db_session_factory, make_session, demo_registry) -> None:
    """批准后前置校验否决（D19/M3.9 挂点）：工具不执行（无 tool_call）、原因回填模型、续跑至完成。"""
    await make_session("sr-13")
    runtime, spec, _, s_events = await _suspend(db_session_factory, demo_registry, "sr-13")
    aid = _approval_id(s_events)
    await ApprovalStore(db_session_factory).decide(aid, approved=True, operator_id="op-1")

    async def veto(tool_name: str, args: Mapping[str, object]) -> str | None:
        return "订单已发货不可退"

    gateway2 = _ScriptedGateway([_text_turn("抱歉，该订单已发货无法退款。")])
    rt2 = AgentRuntime(gateway2, db_session_factory, precheck=veto)
    r_events = [e async for e in rt2.resume(spec, "sr-13", aid)]
    assert [e.type for e in r_events] == [
        EventType.APPROVAL_DECIDED,
        EventType.LLM_CALL,
        EventType.LLM_RESULT,
        EventType.ASSISTANT_MESSAGE,
        EventType.LOOP_TERMINATED,
    ]
    prompt_blob = "\n".join(m.content for m in gateway2.requests[0].messages)
    assert "订单已发货不可退" in prompt_blob  # 否决原因作为观察结果进 prompt
    assert r_events[-1].payload["reason"] == "completed"


async def test_state_transition_cas_rejects_illegal(db_session_factory, make_session) -> None:
    """迁移表之外的路被 expected 参数机器拒绝（C11 同族：条件进 WHERE、输赢看 rowcount）。"""
    await make_session("sr-14")
    st = SessionStateStore(db_session_factory)
    assert await st.transition("sr-14", expected=RunState.IDLE, to=RunState.RUNNING) is True
    assert await st.transition("sr-14", expected=RunState.IDLE, to=RunState.AWAITING_APPROVAL) is False
    assert await st.transition("sr-14", expected=RunState.RUNNING, to=RunState.IDLE) is True

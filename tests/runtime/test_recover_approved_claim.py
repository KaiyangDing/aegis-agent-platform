"""M3.9 交付③：#44 修复——崩溃恢复的"审批认领"分诊支（a+ 支）。

缺陷本体（00 §10.1 #44）：_recover_locked 全程不查审批单——批准落锤与兑现之间
崩溃时，已批准操作被当未配对弃置补话术（坐席白批一次、孤儿 approved 单）。
三窗口用不同手法制造：W1/W2 = decide 后手工翻 T3（模拟 _resume_locked 起步即崩）；
W2.5 = EventWriter 伪造 write-ahead 悬挂（test_loop_recovery._stage_crash 同款）；
W3 = monkeypatch attach_event 一次性炸出真实崩溃现场（M2.12 monkeypatch 中断先例）。
恢复一律走 resume(spec, sid, approval_id=None) 崩溃分诊单入口。零真实调用。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence

import pytest
from sqlalchemy import func, select

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
from aegis.runtime.runtime import AgentRuntime, PrecheckVeto
from aegis.runtime.spec import AgentSpec
from aegis.runtime.store import (
    ApprovalRecord,
    ApprovalStore,
    EventRecord,
    EventWriter,
    RunState,
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
    def __init__(self, scripts: Sequence[Sequence[LLMChunk]]) -> None:
        self.requests: list[LLMRequest] = []
        self._scripts = scripts

    async def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        self.requests.append(req)
        for chunk in self._scripts[len(self.requests) - 1]:
            yield chunk


_REFUND_CALL = ToolCall(id="c-appr", name="demo_refund_apply", arguments_json='{"order_id": "A-9", "amount": 350}')


def _spec(registry) -> AgentSpec:
    return AgentSpec(system_prompt="你是演示客服。", tools=registry.specs(), tenant_config={"approval_threshold": 200})


async def _suspend_and_approve(
    factory, registry, session_id: str, *, flip_t3: bool = True
) -> tuple[AgentSpec, str, list[AgentEvent]]:
    """挂起 + decide(True)；flip_t3=True 再手工翻 T3（模拟批准后恢复起步即崩：
    running、无租约、无 decided 事件——W1/W2 形态）。W3 用 flip_t3=False：
    真实 resume 自己走 T3，预翻会让它的 CAS 打空安静返回、崩不到 attach。"""
    gateway = _ScriptedGateway([_tool_turn(_REFUND_CALL)])
    runtime = AgentRuntime(gateway, factory)
    spec = _spec(registry)
    s_events = [e async for e in runtime.run(spec, session_id, "帮我退 350 元")]
    aid = next(e for e in s_events if e.type is EventType.APPROVAL_REQUESTED).payload["approval_id"]
    assert await ApprovalStore(factory).decide(aid, approved=True, operator_id="op-1") is True
    if flip_t3:
        st = SessionStateStore(factory)
        assert await st.transition(session_id, expected=RunState.AWAITING_APPROVAL, to=RunState.RUNNING) is True
    return spec, aid, s_events


async def _count(factory, session_id: str, event_type: EventType) -> int:
    async with factory() as s:
        return (
            await s.execute(
                select(func.count())
                .select_from(EventRecord)
                .where(EventRecord.session_id == session_id, EventRecord.type == event_type.value)
            )
        ).scalar_one()


async def _approval(factory, aid: str) -> ApprovalRecord:
    async with factory() as s:
        return (await s.execute(select(ApprovalRecord).where(ApprovalRecord.id == aid))).scalar_one()


async def _run_state(factory, session_id: str) -> str:
    from aegis.runtime.store import SessionRecord

    async with factory() as s:
        return (await s.execute(select(SessionRecord.run_state).where(SessionRecord.id == session_id))).scalar_one()


async def test_claim_after_t3_crash_executes_approval(db_session_factory, make_session, demo_registry) -> None:
    """W1：T3 翻转后、decided 事件前崩——认领=补 decided + 原语义执行 + attach + 续跑。

    与 test_resume_approved_executes_and_completes 的事件序完全同构：崩溃恢复
    兑现批准后，用户看到的世界与"没崩过"一致（保事实）。
    """
    await make_session("cl-1")
    spec, aid, s_events = await _suspend_and_approve(db_session_factory, demo_registry, "cl-1")
    runtime = AgentRuntime(_ScriptedGateway([_text_turn("退款已提交，请留意到账。")]), db_session_factory)
    r_events = [e async for e in runtime.resume(spec, "cl-1", None)]
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
    call_event = next(e for e in r_events if e.type is EventType.TOOL_CALL)
    assert (await _approval(db_session_factory, aid)).event_id == call_event.id  # 审计链闭合
    assert await _count(db_session_factory, "cl-1", EventType.TOOL_CALL) == 1  # 执行恰一次
    assert r_events[-1].payload["reason"] == "completed"
    assert await _run_state(db_session_factory, "cl-1") == "idle"


async def test_claim_does_not_duplicate_decided_event(db_session_factory, make_session, demo_registry) -> None:
    """W2：decided 事件已写、执行前崩——认领不重写 decided（全会话恰一条），执行照做。"""
    await make_session("cl-2")
    spec, aid, _ = await _suspend_and_approve(db_session_factory, demo_registry, "cl-2")
    writer = await EventWriter.open(db_session_factory, "cl-2", "crash-resume-1")
    await writer.append(EventType.APPROVAL_DECIDED, {"approval_id": aid, "approved": True, "operator_id": "op-1"})
    runtime = AgentRuntime(_ScriptedGateway([_text_turn("退款已提交。")]), db_session_factory)
    r_events = [e async for e in runtime.resume(spec, "cl-2", None)]
    assert await _count(db_session_factory, "cl-2", EventType.APPROVAL_DECIDED) == 1
    assert await _count(db_session_factory, "cl-2", EventType.TOOL_CALL) == 1
    assert (await _approval(db_session_factory, aid)).event_id is not None
    assert r_events[-1].payload["reason"] == "completed"


async def test_claim_midexecution_reuses_original_key(db_session_factory, make_session, demo_registry) -> None:
    """W2.5：write-ahead 悬挂（执行中途崩）——原幂等键重执行（b 支语义并入认领）+ attach。"""
    await make_session("cl-3")
    spec, aid, _ = await _suspend_and_approve(db_session_factory, demo_registry, "cl-3")
    writer = await EventWriter.open(db_session_factory, "cl-3", "crash-resume-1")
    await writer.append(EventType.APPROVAL_DECIDED, {"approval_id": aid, "approved": True, "operator_id": "op-1"})
    call_event = await writer.append(
        EventType.TOOL_CALL, {"tool_name": "demo_refund_apply", "args": {"order_id": "A-9", "amount": 350}}
    )
    runtime = AgentRuntime(_ScriptedGateway([_text_turn("退款已提交。")]), db_session_factory)
    r_events = [e async for e in runtime.resume(spec, "cl-3", None)]
    result = next(e for e in r_events if e.type is EventType.TOOL_RESULT)
    assert result.payload["tool_call_id"] == call_event.id
    assert result.payload["result"]["idempotency_key"] == call_event.id  # 下游拿到同一把钥匙
    assert await _count(db_session_factory, "cl-3", EventType.TOOL_CALL) == 1  # 绝无第二把
    assert (await _approval(db_session_factory, aid)).event_id == call_event.id
    assert r_events[-1].payload["reason"] == "completed"


async def test_claim_after_terminal_attaches_without_reexecution(
    db_session_factory, make_session, demo_registry, monkeypatch
) -> None:
    """W3：执行完成、attach 前崩（monkeypatch 制造真实现场）——绝不重执行，只补审计链。

    重执行=新 write-ahead 事件 id=新幂等键，下游按新钥匙放行=真双写；
    正解是把已落盘的结果按 _rebuild_working 同款口径取回作 fill。
    """
    await make_session("cl-4")
    # W3 不预翻 T3：真实 resume 自己翻（预翻会让 T3 CAS 打空、安静返回，崩不到 attach）
    spec, aid, _ = await _suspend_and_approve(db_session_factory, demo_registry, "cl-4", flip_t3=False)

    async def boom(self, approval_id, *, event_id):
        raise RuntimeError("模拟 attach 前崩溃")

    monkeypatch.setattr(ApprovalStore, "attach_event", boom)
    crashed = AgentRuntime(_ScriptedGateway([_text_turn("不会走到这。")]), db_session_factory)
    # 直接走审批分诊（approval_id=aid）：decided+tool_call+tool_result 落盘后在 attach 炸掉
    with pytest.raises(RuntimeError, match="模拟"):
        async for _ in crashed.resume(spec, "cl-4", aid):
            pass
    monkeypatch.undo()
    assert await _count(db_session_factory, "cl-4", EventType.TOOL_CALL) == 1
    assert (await _approval(db_session_factory, aid)).event_id is None  # 崩溃现场：已执行未回填

    healing_gateway = _ScriptedGateway([_text_turn("退款已提交，请留意到账。")])
    healer = AgentRuntime(healing_gateway, db_session_factory)
    r_events = [e async for e in healer.resume(spec, "cl-4", None)]
    assert await _count(db_session_factory, "cl-4", EventType.TOOL_CALL) == 1  # 没有第二次执行
    async with db_session_factory() as s:
        call_id = (
            await s.execute(
                select(EventRecord.id).where(
                    EventRecord.session_id == "cl-4", EventRecord.type == EventType.TOOL_CALL.value
                )
            )
        ).scalar_one()
    assert (await _approval(db_session_factory, aid)).event_id == call_id  # 审计链修复
    prompt_blob = "\n".join(m.content for m in healing_gateway.requests[0].messages)
    assert '"refunded": 350' in prompt_blob  # 已落盘结果按原文口径回填进重建序列
    assert r_events[-1].payload["reason"] == "completed"
    assert await _run_state(db_session_factory, "cl-4") == "idle"


async def test_claim_veto_feeds_back_and_leaves_orphan(db_session_factory, make_session, demo_registry) -> None:
    """认领路径同样过前置校验（#8 批准不豁免；M4.1③ 升级）：否决→不执行、observation
    回填续跑、precheck_vetoed 审计事件与 _resume_locked 路径同款（两调用位同一行为）；
    单据保持未回填（无执行事件可挂）——已知边界，14i 拍板Ⅳ 登记。"""
    await make_session("cl-5")
    spec, aid, _ = await _suspend_and_approve(db_session_factory, demo_registry, "cl-5")

    async def veto(tool_name: str, args) -> PrecheckVeto | None:
        return PrecheckVeto("订单状态已变化不可退", detail="快照复核：status=refunded")

    gateway = _ScriptedGateway([_text_turn("抱歉，该订单当前状态无法退款。")])
    runtime = AgentRuntime(gateway, db_session_factory, precheck=veto)
    r_events = [e async for e in runtime.resume(spec, "cl-5", None)]
    assert [e.type for e in r_events] == [
        EventType.APPROVAL_DECIDED,
        EventType.PRECHECK_VETOED,
        EventType.LLM_CALL,
        EventType.LLM_RESULT,
        EventType.ASSISTANT_MESSAGE,
        EventType.LOOP_TERMINATED,
    ]
    assert r_events[1].payload == {
        "approval_id": aid,
        "tool_name": "demo_refund_apply",
        "observation": "订单状态已变化不可退",
        "detail": "快照复核：status=refunded",
    }
    prompt_blob = "\n".join(m.content for m in gateway.requests[0].messages)
    assert "订单状态已变化不可退" in prompt_blob  # observation 作为观察结果进 prompt
    assert "快照复核" not in prompt_blob  # detail 只进审计面，不进模型上下文
    assert await _count(db_session_factory, "cl-5", EventType.TOOL_CALL) == 0
    assert (await _approval(db_session_factory, aid)).event_id is None
    assert r_events[-1].payload["reason"] == "completed"


async def test_terminated_tail_wins_over_claim(db_session_factory, make_session, demo_registry) -> None:
    """a 支优先序：尾事件 loop_terminated 时只修状态——哪怕存在孤儿 approved 单也不重开 run。"""
    await make_session("cl-6")
    spec, aid, _ = await _suspend_and_approve(db_session_factory, demo_registry, "cl-6")

    async def veto(tool_name: str, args) -> PrecheckVeto | None:
        return PrecheckVeto("不可退")

    runtime = AgentRuntime(_ScriptedGateway([_text_turn("无法退款。")]), db_session_factory, precheck=veto)
    r_events = [e async for e in runtime.resume(spec, "cl-6", None)]
    assert r_events[-1].type is EventType.LOOP_TERMINATED  # veto 路径正常收尾，孤儿单仍在
    st = SessionStateStore(db_session_factory)
    assert await st.transition("cl-6", expected=RunState.IDLE, to=RunState.RUNNING) is True  # 模拟 T4 未置回残局
    repair = AgentRuntime(_ScriptedGateway([]), db_session_factory)
    repair_events = [e async for e in repair.resume(spec, "cl-6", None)]
    assert repair_events == []  # a 支：零新事件
    assert (await _approval(db_session_factory, aid)).event_id is None  # 孤儿单不被 a 支代管
    assert await _run_state(db_session_factory, "cl-6") == "idle"

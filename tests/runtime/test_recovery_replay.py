"""M2.12 交付①：中断-恢复逐事件一致——00 §6.2 第 2 项的 CI 强断言（三形态）。

全程 FakeGateway 零真实调用。等价判据 = C31 归一化（normalize_events，M2.6 实名）
+ 本步两件预处理扩展（plans/m2.12 §3.2-5 折叠 + 偏差登记的簿记键剔除）：
- 折叠：llm_call 无同 run 配对 llm_result = 中断的物理痕迹（M2.10"作废重发"的作废段），
  比较前剔除——不折叠则"LLM 中断"形态数学上不可能逐事件一致；
- 剔簿记键 {iteration, input_tokens_est}：resume_run 的 iteration 单 run 重计（M2.9 设计）、
  恢复重建 prompt"保事实不保字节"（K2②）使两键在恢复流必然漂移——它们是 run 簿记/物理
  痕迹；text/tool_calls/args/result/reason 等语义载荷全部保留参与逐事件比较。
确定性中断 = monkeypatch EventWriter.append 计数抛 SimulatedCrash（计划 CrashSink 的
无缝版本——AgentRuntime 内部直调 EventWriter.open 无注入缝，回改生产代码违反本步
"零 aegis/ 改动"铁律；monkeypatch 达成同一计数语义，见 _arm_crash docstring）。
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy import select

from aegis.gateway.schema import LLMChunk, StopChunk, TextDelta, ToolCall, ToolCallChunk, UsageChunk
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.replay import Cassette, CassetteEntry, FakeGateway, normalize_events
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec, TerminationReason
from aegis.runtime.store import ApprovalRecord, ApprovalStore, EventRecord, EventWriter, ToolInvocationRecord
from aegis.runtime.tools import SideEffect, ToolContext, tool

CALLS: list[str] = []
"""真执行观察点：工具每真跑一次记一把幂等键（ctx.tool_call_id=tool_call 事件 id）。
恢复语义断言"不重执行"就看它；每个测试开头 clear()。"""


@tool(side_effect=SideEffect.READ)
async def counted_lookup(ctx: ToolContext, order_id: str) -> dict:
    """计数读工具：形态 A/B 的副作用观察点。"""
    CALLS.append(ctx.tool_call_id)
    return {"order_id": order_id, "status": "已发货"}


def _always_needs_approval(args: Any, tenant_config: Mapping[str, Any]) -> bool:
    return True


@tool(side_effect=SideEffect.WRITE, risk_policy=_always_needs_approval)
async def gated_refund(ctx: ToolContext, order_id: str, amount: int) -> dict:
    """恒审批写工具（形态 C 专用）：批准后真执行同样记幂等键。"""
    CALLS.append(ctx.tool_call_id)
    return {"refunded": amount}


_SPEC = AgentSpec(system_prompt="你是演示客服，请简洁回答。", tools=(counted_lookup, gated_refund))
_LOOKUP_CALL = ToolCall(id="c-look", name="counted_lookup", arguments_json='{"order_id": "A-1"}')
_REFUND_CALL = ToolCall(id="c-ref", name="gated_refund", arguments_json='{"order_id": "A-9", "amount": 350}')
_FINAL_TEXT = "订单 A-1 已发货，请留意物流信息。"
_REFUND_TEXT = "退款已提交，请留意到账通知。"


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


def _entry(chunks: list[LLMChunk]) -> CassetteEntry:
    return CassetteEntry(chunks=tuple(chunks))


def _baseline_cassette(session_id: str) -> Cassette:
    """基线带（内存构造，D12 家族：不强推文件形态）：读工具轮 → 终答轮，无审批无摘要。"""
    return Cassette(
        session_id=session_id,
        scopes={"main": (_entry(_tool_turn(_LOOKUP_CALL)), _entry(_text_turn(_FINAL_TEXT)))},
    )


def _approval_cassette(session_id: str) -> Cassette:
    """形态 C 带：恒审批写工具轮 → 批准续跑后的终答轮。"""
    return Cassette(
        session_id=session_id,
        scopes={"main": (_entry(_tool_turn(_REFUND_CALL)), _entry(_text_turn(_REFUND_TEXT)))},
    )


def _sid(prefix: str) -> str:
    """随机会话 id（M2.11 偏差 #14 教训：测试永不依赖库内既有状态）。"""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class SimulatedCrash(RuntimeError):
    """确定性中断信号：第 N 次 append 前掀翻 run，该次事件不落盘。"""


def _arm_crash(monkeypatch: pytest.MonkeyPatch, crash_at_append_no: int) -> None:
    """monkeypatch EventWriter.append：计数到第 N 次调用时抛 SimulatedCrash。

    与计划的 CrashSink 包装器等价：loop/executor/builder 的全部事件漏斗过同一个
    writer 实例，按 append 调用计数即按事件序计数。触发一次后计数越过阈值，
    恢复段自然走原装路径——无需拆除补丁（pytest 测试尾自动 undo）。
    """
    original = EventWriter.append
    state = {"n": 0}

    async def crashing(self: EventWriter, event_type: EventType, payload: Mapping[str, Any]) -> AgentEvent:
        state["n"] += 1
        if state["n"] == crash_at_append_no:
            raise SimulatedCrash(f"确定性中断：第 {state['n']} 次 append 前（未写入）")
        return await original(self, event_type, payload)

    monkeypatch.setattr(EventWriter, "append", crashing)


async def _db_events(factory, session_id: str) -> list[AgentEvent]:
    """从事实源读全序列（两侧统一地基；产出=落盘的 I4 不变量由 M2.7 测试另证）。"""
    async with factory() as s:
        rows = (
            (await s.execute(select(EventRecord).where(EventRecord.session_id == session_id).order_by(EventRecord.seq)))
            .scalars()
            .all()
        )
    return [
        AgentEvent(
            id=r.id,
            session_id=r.session_id,
            run_id=r.run_id,
            seq=r.seq,
            type=EventType(r.type),
            payload=r.payload,
        )
        for r in rows
    ]


_RUN_BOOKKEEPING_KEYS = ("iteration", "input_tokens_est")


def _fold_half_steps(events: list[AgentEvent]) -> list[AgentEvent]:
    """§3.2-5 折叠：llm_call 无同 run 配对 llm_result（ok/failed/interrupted 均算配对）即剔除。"""
    drop: set[int] = set()
    pending: dict[str, int] = {}
    for i, e in enumerate(events):
        if e.type is EventType.LLM_CALL:
            if e.run_id in pending:
                drop.add(pending[e.run_id])  # 单写者顺序执行下不可达，防御性
            pending[e.run_id] = i
        elif e.type is EventType.LLM_RESULT:
            pending.pop(e.run_id, None)
    drop.update(pending.values())
    return [e for i, e in enumerate(events) if i not in drop]


def _normalized(events: list[AgentEvent]) -> list[dict[str, Any]]:
    """等价预处理三段：折叠 → C31 归一化（M2.6 实名 normalize_events）→ 剔 run 簿记键。"""
    out = normalize_events(_fold_half_steps(events))
    for item in out:
        for key in _RUN_BOOKKEEPING_KEYS:
            item["payload"].pop(key, None)
    return out


def _assert_equivalent(ref: list[AgentEvent], other: list[AgentEvent]) -> None:
    """逐事件比较，失配点名首个分歧索引（C10 响亮精神——绝不只说"不相等"）。"""
    a, b = _normalized(ref), _normalized(other)
    for i, (x, y) in enumerate(zip(a, b, strict=False)):
        assert x == y, f"首个分歧在归一化序列第 {i} 位：\n参照={x}\n恢复={y}"
    assert len(a) == len(b), f"归一化后长度不等：参照 {len(a)} vs 恢复 {len(b)}"


async def _run_full(factory, make_session, session_id: str, cassette: Cassette, user_input: str) -> list[AgentEvent]:
    await make_session(session_id)
    runtime = AgentRuntime(FakeGateway(cassette), factory)
    async for _ in runtime.run(_SPEC, session_id, user_input):
        pass
    return await _db_events(factory, session_id)


async def _run_until_crash(
    factory, make_session, session_id: str, cassette: Cassette, monkeypatch: pytest.MonkeyPatch, crash_at: int
) -> None:
    await make_session(session_id)
    runtime = AgentRuntime(FakeGateway(cassette), factory)
    _arm_crash(monkeypatch, crash_at)
    with pytest.raises(SimulatedCrash):
        async for _ in runtime.run(_SPEC, session_id, "帮我查订单 A-1"):
            pass


async def _resume_crashed(factory, session_id: str, cassette: Cassette, *, main_cursor: int) -> list[AgentEvent]:
    """崩溃恢复：approval_id=None 走 _recover_locked 分诊；恢复段网关按已消费条数设道内游标（C2）。"""
    runtime = AgentRuntime(FakeGateway(cassette, start_cursors={"main": main_cursor}), factory)
    return [e async for e in runtime.resume(_SPEC, session_id)]


def _append_ordinal(ref: list[AgentEvent], event_type: EventType) -> int:
    """参照流中首个该类型事件对应的 append 序号（1-based）——中断点从行为轨迹推导，不硬编码魔数。"""
    return next(i for i, e in enumerate(ref) if e.type is event_type) + 1


async def test_reference_run_replays_deterministically(db_session_factory, make_session) -> None:
    """等价基础设施自证：同一带子两个会话各完整跑一遍，裸 C31 归一化即逐事件相等（防比较器恒真）。"""
    CALLS.clear()
    a_sid, b_sid = _sid("rr-da"), _sid("rr-db")
    a = await _run_full(db_session_factory, make_session, a_sid, _baseline_cassette(a_sid), "帮我查订单 A-1")
    b = await _run_full(db_session_factory, make_session, b_sid, _baseline_cassette(b_sid), "帮我查订单 A-1")
    assert normalize_events(a) == normalize_events(b)  # 干净流无需折叠/剔键即等价
    _assert_equivalent(a, b)  # 全套预处理在干净流上同样成立（预处理不制造差异）


async def test_crash_sink_is_deterministic(db_session_factory, make_session, monkeypatch) -> None:
    """harness 自证：第 N 次 append 前中断 ⇒ 库里恰 N-1 条、末 seq==N-1（中断点可复现才谈得上等价）。"""
    CALLS.clear()
    ref_sid, x_sid = _sid("rr-cs-ref"), _sid("rr-cs")
    ref = await _run_full(db_session_factory, make_session, ref_sid, _baseline_cassette(ref_sid), "帮我查订单 A-1")
    crash_at = _append_ordinal(ref, EventType.TOOL_RESULT) + 1  # tool_result 已提交后、下一事件前
    await _run_until_crash(db_session_factory, make_session, x_sid, _baseline_cassette(x_sid), monkeypatch, crash_at)
    committed = await _db_events(db_session_factory, x_sid)
    assert len(committed) == crash_at - 1
    assert committed[-1].seq == crash_at - 1
    assert committed[-1].type is EventType.TOOL_RESULT


async def test_interrupt_after_tool_result_resumes_identically(db_session_factory, make_session, monkeypatch) -> None:
    """形态 A：工具后中断→恢复。归一化后与参照流逐事件一致；幂等键仍恰一行、工具不重执行。"""
    CALLS.clear()
    ref_sid, x_sid = _sid("rr-a-ref"), _sid("rr-a")
    ref = await _run_full(db_session_factory, make_session, ref_sid, _baseline_cassette(ref_sid), "帮我查订单 A-1")
    crash_at = _append_ordinal(ref, EventType.TOOL_RESULT) + 1
    await _run_until_crash(db_session_factory, make_session, x_sid, _baseline_cassette(x_sid), monkeypatch, crash_at)
    executed_before_resume = len(CALLS)
    resumed = await _resume_crashed(db_session_factory, x_sid, _baseline_cassette(x_sid), main_cursor=1)
    assert len(CALLS) == executed_before_resume, "恢复段重执行了已完成的工具——幂等语义破产"
    assert resumed[-1].payload["reason"] == TerminationReason.COMPLETED.value
    x_events = await _db_events(db_session_factory, x_sid)
    _assert_equivalent(ref, x_events)
    async with db_session_factory() as s:
        rows = (
            (await s.execute(select(ToolInvocationRecord).where(ToolInvocationRecord.session_id == x_sid)))
            .scalars()
            .all()
        )
    assert len(rows) == 1  # 全会话恰一次工具调用审计行（无重复副作用的表侧证据）
    assert rows[0].event_id == next(e.id for e in x_events if e.type is EventType.TOOL_CALL)


async def test_interrupt_mid_llm_discards_and_matches_after_normalize(
    db_session_factory, make_session, monkeypatch
) -> None:
    """形态 B：llm_call 已提交、llm_result 前中断→作废重发。原始流确实含半截（防折叠规则空转），折叠后一致。"""
    CALLS.clear()
    ref_sid, x_sid = _sid("rr-b-ref"), _sid("rr-b")
    ref = await _run_full(db_session_factory, make_session, ref_sid, _baseline_cassette(ref_sid), "帮我查订单 A-1")
    crash_at = _append_ordinal(ref, EventType.LLM_RESULT)  # 恰在首个 llm_result 的 append 上炸
    await _run_until_crash(db_session_factory, make_session, x_sid, _baseline_cassette(x_sid), monkeypatch, crash_at)
    resumed = await _resume_crashed(db_session_factory, x_sid, _baseline_cassette(x_sid), main_cursor=0)
    assert resumed[-1].payload["reason"] == TerminationReason.COMPLETED.value
    x_events = await _db_events(db_session_factory, x_sid)
    calls = [e for e in x_events if e.type is EventType.LLM_CALL]
    results = [e for e in x_events if e.type is EventType.LLM_RESULT]
    assert len(calls) == len(results) + 1, "原始流应含恰一个作废半截 llm_call（中断的物理痕迹）"
    _assert_equivalent(ref, x_events)


async def test_resumed_run_gets_new_run_id_and_continues_seq(db_session_factory, make_session, monkeypatch) -> None:
    """X5 与接续语义：恢复用新 run_id；seq 全会话连续 1..N、恢复段首事件恰接中断段末 seq+1。"""
    CALLS.clear()
    ref_sid, x_sid = _sid("rr-id-ref"), _sid("rr-id")
    ref = await _run_full(db_session_factory, make_session, ref_sid, _baseline_cassette(ref_sid), "帮我查订单 A-1")
    crash_at = _append_ordinal(ref, EventType.TOOL_RESULT) + 1
    await _run_until_crash(db_session_factory, make_session, x_sid, _baseline_cassette(x_sid), monkeypatch, crash_at)
    await _resume_crashed(db_session_factory, x_sid, _baseline_cassette(x_sid), main_cursor=1)
    x_events = await _db_events(db_session_factory, x_sid)
    assert [e.seq for e in x_events] == list(range(1, len(x_events) + 1))
    crashed_run = x_events[0].run_id
    recovery_events = [e for e in x_events if e.run_id != crashed_run]
    assert recovery_events, "恢复段必须存在且使用新 run_id（X5：run_id 每次启动新生成）"
    assert recovery_events[0].seq == crash_at  # EventWriter.open 读流尾接续（store.py:329-336）


async def _suspend_decide_resume(factory, make_session, session_id: str) -> list[AgentEvent]:
    """形态 C 驱动器：挂起（恒审批写工具）→ decide(True) → 恢复单入口续跑 → 返回全事件序列。"""
    await make_session(session_id)
    runtime = AgentRuntime(FakeGateway(_approval_cassette(session_id)), factory)
    suspend_events = [e async for e in runtime.run(_SPEC, session_id, "帮我退 350 元")]
    aid = next(e for e in suspend_events if e.type is EventType.APPROVAL_REQUESTED).payload["approval_id"]
    assert await ApprovalStore(factory).decide(aid, approved=True, operator_id="op-demo")
    resume_rt = AgentRuntime(FakeGateway(_approval_cassette(session_id), start_cursors={"main": 1}), factory)
    async for _ in resume_rt.resume(_SPEC, session_id, aid):
        pass
    return await _db_events(factory, session_id)


async def test_approval_suspend_resume_replays_identically(db_session_factory, make_session) -> None:
    """形态 C 双跑确定性：两个会话各走完整挂起→批准→恢复流，归一化序列逐事件相等。"""
    CALLS.clear()
    a = await _suspend_decide_resume(db_session_factory, make_session, _sid("rr-ca"))
    b = await _suspend_decide_resume(db_session_factory, make_session, _sid("rr-cb"))
    _assert_equivalent(a, b)


async def test_approval_flow_event_shape_snapshot(db_session_factory, make_session) -> None:
    """形态 C 结构快照：事件类型序列钉死；终止 completed；审批单终态 approved + 审计链回填。"""
    CALLS.clear()
    sid = _sid("rr-shape")
    events = await _suspend_decide_resume(db_session_factory, make_session, sid)
    assert [e.type for e in events] == [
        EventType.USER_MESSAGE,
        EventType.LLM_CALL,
        EventType.LLM_RESULT,
        EventType.APPROVAL_REQUESTED,
        EventType.APPROVAL_DECIDED,
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
        EventType.LLM_CALL,
        EventType.LLM_RESULT,
        EventType.ASSISTANT_MESSAGE,
        EventType.LOOP_TERMINATED,
    ]
    assert events[-1].payload["reason"] == TerminationReason.COMPLETED.value
    aid = next(e for e in events if e.type is EventType.APPROVAL_REQUESTED).payload["approval_id"]
    async with db_session_factory() as s:
        row = (await s.execute(select(ApprovalRecord).where(ApprovalRecord.id == aid))).scalar_one()
    assert row.status == "approved"
    assert row.operator_id == "op-demo"
    assert row.event_id == next(e.id for e in events if e.type is EventType.TOOL_CALL)  # attach_event 审计链


async def test_normalize_mismatch_is_loud(db_session_factory, make_session) -> None:
    """比较器自证：篡改一条语义载荷必须响亮失配并点名首个分歧索引（防比较器静默放水）。"""
    CALLS.clear()
    sid = _sid("rr-loud")
    events = await _run_full(db_session_factory, make_session, sid, _baseline_cassette(sid), "帮我查订单 A-1")
    victim = next(i for i, e in enumerate(events) if e.type is EventType.ASSISTANT_MESSAGE)
    tampered = list(events)
    tampered[victim] = replace(events[victim], payload={**events[victim].payload, "content": "被篡改的回答"})
    with pytest.raises(AssertionError, match="首个分歧"):
        _assert_equivalent(events, tampered)

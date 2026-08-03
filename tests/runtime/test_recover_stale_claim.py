"""M4.0② 候选③回归钉子：陈旧审批单不得跨 run 认领。

缺陷本体（M4.0① 探针实测复现）：`_find_unattached_approved` 无 run 维度无时间窗，
而 veto 单永远满足 `approved ∧ event_id IS NULL`（demo_hitl 段 D 亲手断言过该状态、
test_recover_approved_claim.py:240 钉过）——此后**任意一次无悬挂工具的崩溃恢复**
都会捞到它进 a+ 认领支：本该走 c 支（半截 llm_call 作废重发）的新 run 被劫持成
"兑现一张几轮前就已了结的批准"。探针实测两个后果：
- 3a：恢复分诊走错支（veto 观察再次进 prompt）——用户新消息仍在（`_rebuild_working`
  带全量事件），故记忆档案"用户刚问的话被完全忽略"的原述已修正；
- 3b：precheck 此刻若通过（订单状态恢复可退），**执行一次本轮从未请求的写操作**。

判据修法（00 §10.1 #50 建议向）：认领前查"该 approval_requested 之后是否已有
loop_terminated"——单据所属的那个 run 已经收尾，就不是"崩在批准与兑现之间"。
只读既有事实、无新字段、无新查询（`rows` 已是全量事件按 seq 排序）。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence

import pytest
from sqlalchemy import func, select, update

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
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec
from aegis.runtime.store import ApprovalRecord, ApprovalStore, EventRecord, RunState, SessionRecord, SessionStateStore


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


class _CrashGateway:
    """首次拉流即裸炸——模拟进程级崩溃。loop 先写 llm_call 再拉流，故崩后
    尾事件=llm_call、无悬挂 tool_call：这正是 c 支（作废重发）的形态。"""

    async def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        raise RuntimeError("模拟进程崩溃")
        yield  # pragma: no cover —— 使函数成为异步生成器


_REFUND_CALL = ToolCall(id="c-appr", name="demo_refund_apply", arguments_json='{"order_id": "A-9", "amount": 350}')


def _spec(registry) -> AgentSpec:
    return AgentSpec(system_prompt="你是演示客服。", tools=registry.specs(), tenant_config={"approval_threshold": 200})


async def _veto(tool_name: str, args) -> str | None:
    return "订单状态已变化不可退"


async def _make_orphan_veto_session(factory, registry, session_id: str) -> tuple[AgentSpec, str]:
    """制造陈旧 veto 单：挂起 → 批准 → precheck 否决 → run 正常收尾。

    终态 = 会话 idle、单据 approved ∧ event_id IS NULL（无执行事件可挂）。
    这是 14i 拍板Ⅳ 登记的合法已知边界，不是缺陷——缺陷是它此后会被反复认领。
    """
    runtime = AgentRuntime(_ScriptedGateway([_tool_turn(_REFUND_CALL)]), factory)
    spec = _spec(registry)
    events = [e async for e in runtime.run(spec, session_id, "帮我退 350 元")]
    aid = next(e for e in events if e.type is EventType.APPROVAL_REQUESTED).payload["approval_id"]
    assert await ApprovalStore(factory).decide(aid, approved=True, operator_id="op-1") is True
    st = SessionStateStore(factory)
    assert await st.transition(session_id, expected=RunState.AWAITING_APPROVAL, to=RunState.RUNNING) is True
    healer = AgentRuntime(_ScriptedGateway([_text_turn("抱歉，该订单当前状态无法退款。")]), factory, precheck=_veto)
    tail = [e async for e in healer.resume(spec, session_id, None)]
    assert tail[-1].payload["reason"] == "completed"  # veto 路径正常收尾
    async with factory() as s:
        row = (await s.execute(select(ApprovalRecord).where(ApprovalRecord.id == aid))).scalar_one()
    assert row.status == "approved" and row.event_id is None  # 陈旧孤儿单成型
    return spec, aid


async def _crash_new_run(factory, spec: AgentSpec, session_id: str, message: str) -> None:
    """在一个全新 run 的 llm_call 之后崩掉，并把租约清空（等价于租约过期被 steal）。"""
    with pytest.raises(RuntimeError, match="模拟进程崩溃"):
        async for _ in AgentRuntime(_CrashGateway(), factory).run(spec, session_id, message):
            pass
    async with factory() as s:
        async with s.begin():
            await s.execute(
                update(SessionRecord)
                .where(SessionRecord.id == session_id)
                .values(lease_owner=None, lease_expires_at=None)
            )


async def _count(factory, session_id: str, event_type: EventType) -> int:
    async with factory() as s:
        return (
            await s.execute(
                select(func.count())
                .select_from(EventRecord)
                .where(EventRecord.session_id == session_id, EventRecord.type == event_type.value)
            )
        ).scalar_one()


async def test_stale_veto_claim_does_not_hijack_new_run(db_session_factory, make_session, demo_registry) -> None:
    """核心钉子：陈旧 veto 单所属 run 已 loop_terminated → 新 run 崩溃恢复不得认领它。

    正确行为 = 走 c/d 支（不补事件、直接续跑），veto 话术**不再**进重建 prompt。
    """
    await make_session("st-1")
    spec, _aid = await _make_orphan_veto_session(db_session_factory, demo_registry, "st-1")
    await _crash_new_run(db_session_factory, spec, "st-1", "帮我查订单 B-7 的物流")

    healer_gw = _ScriptedGateway([_text_turn("好的，正在为您查询物流。")])
    r_events = [e async for e in AgentRuntime(healer_gw, db_session_factory, precheck=_veto).resume(spec, "st-1", None)]

    prompt_blob = "\n".join(m.content for m in healer_gw.requests[0].messages)
    assert "审批已通过但前置校验未过" not in prompt_blob  # 未被陈旧单劫持
    assert "帮我查订单 B-7 的物流" in prompt_blob  # 本轮问题照常在场
    assert [e.type for e in r_events] == [
        EventType.LLM_CALL,
        EventType.LLM_RESULT,
        EventType.ASSISTANT_MESSAGE,
        EventType.LOOP_TERMINATED,
    ]
    assert r_events[-1].payload["reason"] == "completed"


async def test_stale_claim_never_executes_unrequested_write(db_session_factory, make_session, demo_registry) -> None:
    """3b 支（危害最重）：precheck 此刻放行也绝不执行本轮从未请求的写操作。

    未修代码在此会退款 350 元——一次用户没要过、模型没提过的真实副作用。
    """
    await make_session("st-2")
    spec, _aid = await _make_orphan_veto_session(db_session_factory, demo_registry, "st-2")
    assert await _count(db_session_factory, "st-2", EventType.TOOL_CALL) == 0  # veto 从未执行

    await _crash_new_run(db_session_factory, spec, "st-2", "帮我查订单 B-7 的物流")
    # precheck=None 模拟"订单状态已恢复可退"——未修代码此时会真的执行
    r_events = [
        e
        async for e in AgentRuntime(_ScriptedGateway([_text_turn("好的。")]), db_session_factory).resume(
            spec, "st-2", None
        )
    ]

    assert await _count(db_session_factory, "st-2", EventType.TOOL_CALL) == 0  # 零副作用
    assert not [e for e in r_events if e.type is EventType.TOOL_CALL]


async def test_genuine_claim_still_works_after_fix(db_session_factory, make_session, demo_registry) -> None:
    """反向对照（防修过头）：真正的"崩在批准与兑现之间"必须照常认领。

    与 test_claim_after_t3_crash_executes_approval 同形态——该 run 无 loop_terminated，
    新判据不该拦住它。修复若把 a+ 支整个拦死，本测试立刻变红。
    """
    await make_session("st-3")
    runtime = AgentRuntime(_ScriptedGateway([_tool_turn(_REFUND_CALL)]), db_session_factory)
    spec = _spec(demo_registry)
    events = [e async for e in runtime.run(spec, "st-3", "帮我退 350 元")]
    aid = next(e for e in events if e.type is EventType.APPROVAL_REQUESTED).payload["approval_id"]
    assert await ApprovalStore(db_session_factory).decide(aid, approved=True, operator_id="op-1") is True
    st = SessionStateStore(db_session_factory)
    assert await st.transition("st-3", expected=RunState.AWAITING_APPROVAL, to=RunState.RUNNING) is True

    healer = AgentRuntime(_ScriptedGateway([_text_turn("退款已提交。")]), db_session_factory)
    r_events = [e async for e in healer.resume(spec, "st-3", None)]

    assert [e.type for e in r_events] == [
        EventType.APPROVAL_DECIDED,
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
        EventType.LLM_CALL,
        EventType.LLM_RESULT,
        EventType.ASSISTANT_MESSAGE,
        EventType.LOOP_TERMINATED,
    ]
    async with db_session_factory() as s:
        row = (await s.execute(select(ApprovalRecord).where(ApprovalRecord.id == aid))).scalar_one()
    assert row.event_id is not None  # 审计链照常闭合

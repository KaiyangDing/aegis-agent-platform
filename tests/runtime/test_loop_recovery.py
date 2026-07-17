"""M2.10 交付②：两类恢复语义——半截工具凭原幂等键重执行 / 半截 LLM 作废重发 / 续租自毁。

崩溃现场用 EventWriter 直写事件流伪造（staged run 的 run_state 置 running、租约留空——
偏差 #5 的 NULL 幽灵形态，恰是 kill -9 后 reaper 眼中的样子）；恢复走
resume(spec, sid, approval_id=None) 单入口。零真实调用。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Sequence

import pytest
from sqlalchemy import func, select

from aegis.core.config import Settings
from aegis.gateway.schema import (
    LLMChunk,
    LLMRequest,
    StopChunk,
    TextDelta,
    UsageChunk,
)
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec
from aegis.runtime.store import (
    EventRecord,
    EventWriter,
    InvocationStatus,
    LeaseLost,
    RunState,
    SessionRecord,
    SessionStateStore,
    ToolInvocationRecord,
)


def _text_turn(text: str) -> list[LLMChunk]:
    return [
        TextDelta(text=text),
        UsageChunk(model="qwen-plus", prompt_tokens=20, completion_tokens=7),
        StopChunk(reason="end_turn"),
    ]


class _ScriptedGateway:
    def __init__(self, scripts: Sequence[Sequence[LLMChunk]]) -> None:
        self.requests: list[LLMRequest] = []
        self._scripts = scripts

    async def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        self.requests.append(req)
        for chunk in self._scripts[len(self.requests) - 1]:
            yield chunk


class _SlowGateway:
    """每个 chunk 前微睡——给续租心跳的死亡让出调度窗（自毁测试专用）。"""

    def __init__(self, text: str) -> None:
        self._text = text

    async def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        for chunk in _text_turn(self._text):
            await asyncio.sleep(0.03)
            yield chunk


async def _stage_crash(
    factory,
    session_id: str,
    *,
    calls: Sequence[tuple[str, str, str]],
    finished: int,
    tail_terminated: bool = False,
) -> list[AgentEvent]:
    """伪造崩溃现场：user_message + llm_call + llm_result(工具轮) + 前 finished 个调用的
    完整配对 + 第 finished+1 个只留 write-ahead（悬挂）；run_state 置 running、租约留空。"""
    writer = await EventWriter.open(factory, session_id, "crash-run-1")
    staged: list[AgentEvent] = []
    staged.append(await writer.append(EventType.USER_MESSAGE, {"content": "帮我查订单 A-1 顺便退 80 元"}))
    staged.append(await writer.append(EventType.LLM_CALL, {"iteration": 1, "tier": "standard", "input_tokens_est": 30}))
    tool_calls = [{"id": cid, "name": name, "arguments_json": args_json} for cid, name, args_json in calls]
    staged.append(
        await writer.append(
            EventType.LLM_RESULT,
            {
                "iteration": 1,
                "status": "ok",
                "text": "",
                "tool_calls": tool_calls,
                "stop_reason": "tool_calls",
                "model": "qwen-plus",
                "usage": {"prompt_tokens": 30, "completion_tokens": 12},
                "cached": False,
                "output_tokens_est": 12,
                "latency_ms": 5,
            },
        )
    )
    import json as _json

    for i, (_cid, name, args_json) in enumerate(calls):
        if i > finished:
            break
        call_event = await writer.append(EventType.TOOL_CALL, {"tool_name": name, "args": _json.loads(args_json)})
        staged.append(call_event)
        if i < finished:  # 前 finished 个闭合；第 finished+1 个（下标 finished）悬挂
            staged.append(
                await writer.append(
                    EventType.TOOL_RESULT,
                    {
                        "tool_call_id": call_event.id,
                        "result": {"ok": True, "i": i},
                        "latency_ms": 3,
                        "retry_count": 0,
                        "digest": "ok",
                    },
                )
            )
    if tail_terminated:
        staged.append(
            await writer.append(EventType.LOOP_TERMINATED, {"reason": "completed", "iteration": 1, "detail": "staged"})
        )
    st = SessionStateStore(factory)
    assert await st.transition(session_id, expected=RunState.IDLE, to=RunState.RUNNING) is True
    return staged


def _spec(registry) -> AgentSpec:
    return AgentSpec(system_prompt="你是演示客服。", tools=registry.specs(), tenant_config={"approval_threshold": 200})


async def _count(factory, session_id: str, event_type: EventType) -> int:
    async with factory() as s:
        return (
            await s.execute(
                select(func.count())
                .select_from(EventRecord)
                .where(EventRecord.session_id == session_id, EventRecord.type == event_type.value)
            )
        ).scalar_one()


async def test_renew_failure_self_destructs_without_events(db_session_factory, make_session, demo_registry) -> None:
    """C2 协议一/二：续租打空 → LeaseLost 传播、立即自毁——绝不出现终止收尾类事件。

    断言贴语义不贴时序（首版在 CI 翻车的教训）："不写任何进一步事件"的精确含义是
    **感知丢锁之后**；感知是事件间检查点、有粒度——窗口内的在途事件（如 llm_result）
    落盘与否取决于死亡时刻，不是自毁语义的一部分（真正防线=唯一约束）。时序无关的
    不变量是：loop_terminated 与兜底 assistant_message（_terminate 产物）必然缺席。
    """
    await make_session("lr-1")

    class _DeadLeases:
        async def acquire(self, session_id, *, owner, ttl_s, now=None):
            return 1

        async def renew(self, session_id, *, owner, generation, ttl_s):
            return False  # 第一跳即旁落

        async def release(self, session_id, *, owner, generation):
            return False

    runtime = AgentRuntime(
        _SlowGateway("慢慢说完这句话。"),
        db_session_factory,
        settings=Settings(lease_ttl_s=0.05, lease_renew_interval_s=0.01),
    )
    runtime._leases = _DeadLeases()  # type: ignore[assignment]  # 测试替身：renew 恒 False
    with pytest.raises(LeaseLost):
        async for _ in runtime.run(_spec(demo_registry), "lr-1", "你好"):
            pass
    assert await _count(db_session_factory, "lr-1", EventType.LOOP_TERMINATED) == 0
    assert await _count(db_session_factory, "lr-1", EventType.ASSISTANT_MESSAGE) == 0


async def test_recover_dangling_read_tool_reexecutes(db_session_factory, make_session, demo_registry) -> None:
    """半截读工具：凭原事件 id 重执行——tool_result 带原 tool_call_id、投影行闭合 SUCCEEDED。"""
    await make_session("lr-2")
    staged = await _stage_crash(
        db_session_factory, "lr-2", calls=[("c-1", "demo_order_query", '{"order_id": "A-1"}')], finished=0
    )
    dangling_id = next(e.id for e in staged if e.type is EventType.TOOL_CALL)
    runtime = AgentRuntime(_ScriptedGateway([_text_turn("订单已发货。")]), db_session_factory)
    r_events = [e async for e in runtime.resume(_spec(demo_registry), "lr-2", None)]
    result = next(e for e in r_events if e.type is EventType.TOOL_RESULT)
    assert result.payload["tool_call_id"] == dangling_id
    assert await _count(db_session_factory, "lr-2", EventType.TOOL_CALL) == 1  # 绝无第二把幂等键
    async with db_session_factory() as s:
        inv = (
            await s.execute(select(ToolInvocationRecord).where(ToolInvocationRecord.event_id == dangling_id))
        ).scalar_one()
    assert inv.status == InvocationStatus.SUCCEEDED
    assert r_events[-1].payload["reason"] == "completed"


async def test_recover_dangling_write_tool_reuses_idempotency_key(
    db_session_factory, make_session, demo_registry
) -> None:
    """半截写工具：幂等键复用自证——handler 回显的 ctx.tool_call_id 恰是原 write-ahead 事件 id。"""
    await make_session("lr-3")
    staged = await _stage_crash(
        db_session_factory,
        "lr-3",
        calls=[("c-1", "demo_refund_apply", '{"order_id": "A-1", "amount": 80}')],
        finished=0,
    )
    dangling_id = next(e.id for e in staged if e.type is EventType.TOOL_CALL)
    runtime = AgentRuntime(_ScriptedGateway([_text_turn("退款已提交。")]), db_session_factory)
    r_events = [e async for e in runtime.resume(_spec(demo_registry), "lr-3", None)]
    result = next(e for e in r_events if e.type is EventType.TOOL_RESULT)
    assert result.payload["result"]["idempotency_key"] == dangling_id  # 下游拿到同一把钥匙
    assert await _count(db_session_factory, "lr-3", EventType.TOOL_CALL) == 1
    assert r_events[-1].payload["reason"] == "completed"


async def test_recover_missing_tool_writes_tool_error(db_session_factory, make_session, demo_registry) -> None:
    """恢复期工具缺失（spec 演进）：以原 id 写 tool_error 闭合，错误回填模型、循环续至完成。"""
    await make_session("lr-4")
    staged = await _stage_crash(db_session_factory, "lr-4", calls=[("c-1", "ghost_tool", '{"x": 1}')], finished=0)
    dangling_id = next(e.id for e in staged if e.type is EventType.TOOL_CALL)
    runtime = AgentRuntime(_ScriptedGateway([_text_turn("该操作暂不可用。")]), db_session_factory)
    r_events = [e async for e in runtime.resume(_spec(demo_registry), "lr-4", None)]
    err = next(e for e in r_events if e.type is EventType.TOOL_ERROR)
    assert err.payload["tool_call_id"] == dangling_id
    assert r_events[-1].payload["reason"] == "completed"


async def test_recover_dangling_llm_call_reissues(db_session_factory, make_session, demo_registry) -> None:
    """半截 LLM：作废重发——不为旧调用补任何事件，新 llm_call 自然出现，run 正常收尾。"""
    await make_session("lr-5")
    writer = await EventWriter.open(db_session_factory, "lr-5", "crash-run-1")
    await writer.append(EventType.USER_MESSAGE, {"content": "帮我查订单"})
    await writer.append(EventType.LLM_CALL, {"iteration": 1, "tier": "standard", "input_tokens_est": 20})
    st = SessionStateStore(db_session_factory)
    assert await st.transition("lr-5", expected=RunState.IDLE, to=RunState.RUNNING) is True
    runtime = AgentRuntime(_ScriptedGateway([_text_turn("已在派送中。")]), db_session_factory)
    r_events = [e async for e in runtime.resume(_spec(demo_registry), "lr-5", None)]
    assert await _count(db_session_factory, "lr-5", EventType.LLM_CALL) == 2  # 旧的作废、新的出现
    assert await _count(db_session_factory, "lr-5", EventType.LLM_RESULT) == 1  # 只有新调用有结果
    assert r_events[-1].payload["reason"] == "completed"


async def test_recover_after_terminated_repairs_state_only(db_session_factory, make_session, demo_registry) -> None:
    """尾事件 loop_terminated（T4 未置回的残局）：只修状态归 idle + 清租约，零新事件。"""
    await make_session("lr-6")
    await _stage_crash(db_session_factory, "lr-6", calls=[], finished=-1, tail_terminated=True)
    before = await _count(db_session_factory, "lr-6", EventType.LOOP_TERMINATED)
    runtime = AgentRuntime(_ScriptedGateway([]), db_session_factory)
    r_events = [e async for e in runtime.resume(_spec(demo_registry), "lr-6", None)]
    assert r_events == []
    assert await _count(db_session_factory, "lr-6", EventType.LOOP_TERMINATED) == before
    async with db_session_factory() as s:
        row = (await s.execute(select(SessionRecord).where(SessionRecord.id == "lr-6"))).scalar_one()
    assert row.run_state == RunState.IDLE.value
    assert row.lease_owner is None


async def test_recovered_run_new_run_id_seq_continues(db_session_factory, make_session, demo_registry) -> None:
    """恢复出的新 run：run_id 全新、seq 无缝接续旧流（EventWriter.open 读流尾）。"""
    await make_session("lr-7")
    staged = await _stage_crash(
        db_session_factory, "lr-7", calls=[("c-1", "demo_order_query", '{"order_id": "A-1"}')], finished=0
    )
    runtime = AgentRuntime(_ScriptedGateway([_text_turn("订单已发货。")]), db_session_factory)
    r_events = [e async for e in runtime.resume(_spec(demo_registry), "lr-7", None)]
    assert r_events[0].seq == staged[-1].seq + 1
    assert [e.seq for e in r_events] == list(range(r_events[0].seq, r_events[0].seq + len(r_events)))
    assert len({e.run_id for e in r_events}) == 1
    assert r_events[0].run_id != "crash-run-1"

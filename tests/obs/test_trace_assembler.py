"""M4.1 交付①：TraceAssembler（aegis/obs/trace.py）——事件流+账本 → trace 视图。

造数走 EventWriter.open/append 真实路径（投影同事务派生与生产一致；
tool_result/tool_error 的 tool_call_id 必须指向真实 tool_call 事件 id，
否则投影层 ProjectionError——write-ahead 顺序是被钉死的）；账本行用 ORM 构造。
savepoint 夹具下 PG now() 冻结在外层事务开始时刻（m4 计划 §7-1 的反面），
llm 耗时断言改为显式 UPDATE created_at 构造已知时钟——断言配对算法，
不断言测试机的调度延迟（红线 5：时序敏感断言不进 CI）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select, text

from aegis.gateway.metering import UsageRecord
from aegis.obs.trace import TraceAssembler
from aegis.runtime.events import EventType
from aegis.runtime.store import EventRecord, EventWriter, SessionRecord


def _ids() -> tuple[str, str]:
    suffix = uuid4().hex[:8]
    return f"t-tr-{suffix}", f"tr-{suffix}"


async def _seed_session(factory, tid: str, sid: str) -> SessionRecord:
    async with factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=sid, tenant_id=tid, user_id="u-tr1"))
    async with factory() as s:
        return (await s.execute(select(SessionRecord).where(SessionRecord.id == sid))).scalar_one()


async def _set_created_at(factory, sid: str, stamps: dict[int, datetime]) -> None:
    """显式构造 DB 时钟：seq → created_at（savepoint 世界 now() 冻结，见模块头）。"""
    async with factory() as s:
        async with s.begin():
            for seq, at in stamps.items():
                await s.execute(
                    text("UPDATE events SET created_at = :at WHERE session_id = :sid AND seq = :seq"),
                    {"at": at, "sid": sid, "seq": seq},
                )


async def test_events_ordered_by_seq_and_grouped_by_run(db_session_factory) -> None:
    """事件按 seq 全序、按 run 分组保首现顺序；trace_id ≡ session_id（X5）。"""
    tid, sid = _ids()
    row = await _seed_session(db_session_factory, tid, sid)
    w1 = await EventWriter.open(db_session_factory, sid, "run-tr-1")
    await w1.append(EventType.USER_MESSAGE, {"content": "查订单"})
    await w1.append(EventType.ASSISTANT_MESSAGE, {"content": "已发货。"})
    w2 = await EventWriter.open(db_session_factory, sid, "run-tr-2")
    await w2.append(EventType.USER_MESSAGE, {"content": "再查一次"})
    view = await TraceAssembler(db_session_factory).assemble(row)
    assert view.trace_id == sid
    assert view.session_id == sid
    assert view.tenant_id == tid
    assert view.run_state == row.run_state
    assert [r.run_id for r in view.runs] == ["run-tr-1", "run-tr-2"]
    assert [e.seq for e in view.runs[0].events] == [1, 2]
    assert [e.seq for e in view.runs[1].events] == [3]
    assert view.runs[0].events[0].type == "user_message"


async def test_termination_reason_from_last_loop_terminated(db_session_factory) -> None:
    """termination_reason=该 run 最后一条 loop_terminated 的 reason；无终局的 run 为 None。"""
    tid, sid = _ids()
    row = await _seed_session(db_session_factory, tid, sid)
    w1 = await EventWriter.open(db_session_factory, sid, "run-tr-1")
    await w1.append(EventType.USER_MESSAGE, {"content": "hi"})
    await w1.append(EventType.LOOP_TERMINATED, {"reason": "completed", "iteration": 1, "detail": ""})
    w2 = await EventWriter.open(db_session_factory, sid, "run-tr-2")
    await w2.append(EventType.USER_MESSAGE, {"content": "again"})
    view = await TraceAssembler(db_session_factory).assemble(row)
    assert view.runs[0].termination_reason == "completed"
    assert view.runs[1].termination_reason is None


async def test_llm_duration_from_db_clock_pairing(db_session_factory) -> None:
    """llm_result 耗时=与同 run 前一条 llm_call 的 created_at 差；无前驱=null 不猜。"""
    tid, sid = _ids()
    row = await _seed_session(db_session_factory, tid, sid)
    w = await EventWriter.open(db_session_factory, sid, "run-tr-1")
    await w.append(EventType.LLM_CALL, {"tier": "standard"})
    await w.append(EventType.LLM_RESULT, {"status": "ok", "text": "好的"})
    w2 = await EventWriter.open(db_session_factory, sid, "run-tr-orphan")
    await w2.append(EventType.LLM_RESULT, {"status": "ok", "text": "无前驱"})
    t0 = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)
    await _set_created_at(db_session_factory, sid, {1: t0, 2: t0 + timedelta(milliseconds=1500)})
    view = await TraceAssembler(db_session_factory).assemble(row)
    assert view.runs[0].events[0].duration_ms is None  # llm_call 本身不配耗时
    assert view.runs[0].events[1].duration_ms == 1500
    assert view.runs[1].events[0].duration_ms is None  # 无前驱不猜


async def test_retry_llm_call_pairs_with_latest(db_session_factory) -> None:
    """作废重发（D10）：llm_result 与最近一条 llm_call 配对，不与作废半截配对。"""
    tid, sid = _ids()
    row = await _seed_session(db_session_factory, tid, sid)
    w = await EventWriter.open(db_session_factory, sid, "run-tr-1")
    await w.append(EventType.LLM_CALL, {"tier": "standard"})  # 半截：无 result
    await w.append(EventType.LLM_CALL, {"tier": "standard"})  # 重发
    await w.append(EventType.LLM_RESULT, {"status": "ok", "text": "ok"})
    t0 = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)
    await _set_created_at(
        db_session_factory, sid, {1: t0, 2: t0 + timedelta(seconds=10), 3: t0 + timedelta(seconds=11)}
    )
    view = await TraceAssembler(db_session_factory).assemble(row)
    assert view.runs[0].events[2].duration_ms == 1000  # 距重发 1s，不是距首发 11s


async def test_tool_duration_read_from_payload(db_session_factory) -> None:
    """tool_result/tool_error 耗时直读 payload.latency_ms（executor 实测、投影同源）；缺失=null。"""
    tid, sid = _ids()
    row = await _seed_session(db_session_factory, tid, sid)
    w = await EventWriter.open(db_session_factory, sid, "run-tr-1")
    c1 = await w.append(EventType.TOOL_CALL, {"tool_name": "order_query", "args": {"order_id": "AZ-1001"}})
    await w.append(EventType.TOOL_RESULT, {"tool_call_id": c1.id, "result": {"ok": True}, "latency_ms": 42})
    c2 = await w.append(EventType.TOOL_CALL, {"tool_name": "logistics_query", "args": {"order_id": "AZ-1001"}})
    await w.append(EventType.TOOL_ERROR, {"tool_call_id": c2.id, "error": "上游超时", "latency_ms": 7})
    c3 = await w.append(EventType.TOOL_CALL, {"tool_name": "order_query", "args": {"order_id": "AZ-1002"}})
    await w.append(EventType.TOOL_RESULT, {"tool_call_id": c3.id, "result": {}})
    view = await TraceAssembler(db_session_factory).assemble(row)
    events = view.runs[0].events
    assert [e.duration_ms for e in events] == [None, 42, None, 7, None, None]


async def test_usage_aggregated_from_ledger(db_session_factory) -> None:
    """账本按会话聚合 requests/tokens/cached_hits/cost；他会话行不串。"""
    tid, sid = _ids()
    row = await _seed_session(db_session_factory, tid, sid)
    w = await EventWriter.open(db_session_factory, sid, "run-tr-1")
    await w.append(EventType.USER_MESSAGE, {"content": "hi"})
    async with db_session_factory() as s:
        async with s.begin():
            s.add(
                UsageRecord(
                    request_id="rq-tr-1",
                    tenant_id=tid,
                    session_id=sid,
                    tier="standard",
                    provider="bailian",
                    model="m-a",
                    prompt_tokens=100,
                    completion_tokens=50,
                    cached=False,
                    cost=Decimal("0.001000"),
                )
            )
            s.add(
                UsageRecord(
                    request_id="rq-tr-2",
                    tenant_id=tid,
                    session_id=sid,
                    tier="fast",
                    provider="bailian",
                    model="m-b",
                    prompt_tokens=10,
                    completion_tokens=5,
                    cached=True,
                    cost=Decimal("0"),
                )
            )
            s.add(
                UsageRecord(
                    request_id="rq-tr-3",
                    tenant_id=tid,
                    session_id=f"other-{sid}",
                    tier="fast",
                    provider="bailian",
                    model="m-b",
                    prompt_tokens=7,
                    completion_tokens=3,
                    cached=False,
                    cost=Decimal("0.000500"),
                )
            )
    view = await TraceAssembler(db_session_factory).assemble(row)
    assert view.usage.requests == 2
    assert view.usage.prompt_tokens == 110
    assert view.usage.completion_tokens == 55
    assert view.usage.cached_hits == 1
    assert view.usage.cost == Decimal("0.001")


async def test_usage_cost_serializes_as_exact_decimal_string(db_session_factory) -> None:
    """cost 出线形态=精确小数字符串（pydantic v2 JSON 缺省——M3.1"钱不过 float"契约沿用）。"""
    tid, sid = _ids()
    row = await _seed_session(db_session_factory, tid, sid)
    async with db_session_factory() as s:
        async with s.begin():
            s.add(
                UsageRecord(
                    request_id="rq-tr-4",
                    tenant_id=tid,
                    session_id=sid,
                    tier="fast",
                    provider="bailian",
                    model="m-b",
                    prompt_tokens=1,
                    completion_tokens=1,
                    cached=False,
                    cost=Decimal("0.001234"),
                )
            )
    view = await TraceAssembler(db_session_factory).assemble(row)
    cost = view.model_dump(mode="json")["usage"]["cost"]
    assert isinstance(cost, str)
    assert Decimal(cost) == Decimal("0.001234")


async def test_payload_masked_in_view_but_raw_in_store(db_session_factory) -> None:
    """出口脱敏、事实源原文：视图 payload 打码，events 表一字不动（脱敏绝不进写路径）。"""
    tid, sid = _ids()
    row = await _seed_session(db_session_factory, tid, sid)
    w = await EventWriter.open(db_session_factory, sid, "run-tr-1")
    await w.append(EventType.ASSISTANT_MESSAGE, {"content": "已登记手机号 13812345678。"})
    view = await TraceAssembler(db_session_factory).assemble(row)
    content = view.runs[0].events[0].payload["content"]
    assert "***phone_cn***" in content
    assert "13812345678" not in content
    async with db_session_factory() as s:
        stored = (await s.execute(select(EventRecord.payload).where(EventRecord.session_id == sid))).scalar_one()
    assert stored["content"] == "已登记手机号 13812345678。"


async def test_assemble_is_readonly(db_session_factory) -> None:
    """装配是只读操作：跑两遍，events 行数不变（关键不变量：零写入）。"""
    tid, sid = _ids()
    row = await _seed_session(db_session_factory, tid, sid)
    w = await EventWriter.open(db_session_factory, sid, "run-tr-1")
    await w.append(EventType.USER_MESSAGE, {"content": "hi"})

    async def _count() -> int:
        async with db_session_factory() as s:
            return len((await s.execute(select(EventRecord.id).where(EventRecord.session_id == sid))).all())

    before = await _count()
    await TraceAssembler(db_session_factory).assemble(row)
    await TraceAssembler(db_session_factory).assemble(row)
    assert await _count() == before == 1

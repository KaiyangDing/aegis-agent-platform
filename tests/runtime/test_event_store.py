"""M2.2 交付②：单写者写入器——seq 接续、幽灵写入、围栏终态、白名单重试。"""

from __future__ import annotations

from itertools import count

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from aegis.runtime.events import EventType
from aegis.runtime.store import (
    EventRecord,
    EventStoreUnavailable,
    EventWriteFenced,
    EventWriter,
    SessionFactory,
)


def _ids(prefix: str = "e"):
    c = count(1)
    return lambda: f"{prefix}-{next(c)}"


def _sleep_recorder(into: list[float]):
    async def _sleep(delay: float) -> None:
        into.append(delay)

    return _sleep


class _FlakyFactory:
    """前 fail_times 次调用抛连接级故障，之后透传真工厂——重试路径的手术刀。"""

    def __init__(self, real: SessionFactory, fail_times: int, exc: type[Exception] = OperationalError) -> None:
        self.real = real
        self.remaining = fail_times
        self.exc = exc
        self.calls = 0

    def __call__(self) -> AsyncSession:
        self.calls += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise self.exc("boom", None, RuntimeError("connection refused"))
        return self.real()


async def test_append_assigns_sequential_seq_and_persists(db_session_factory) -> None:
    w = await EventWriter.open(db_session_factory, "s-1", "r-1", id_factory=_ids())
    e1 = await w.append(EventType.USER_MESSAGE, {"content": "你好"})
    e2 = await w.append(EventType.LLM_CALL, {"tier": "standard"})
    e3 = await w.append(EventType.LLM_RESULT, {"ok": True})
    assert (e1.seq, e2.seq, e3.seq) == (1, 2, 3)
    assert e1.id == "e-1" and e1.type is EventType.USER_MESSAGE and e1.schema_version == 1
    async with db_session_factory() as s:
        n = (
            await s.execute(select(func.count()).select_from(EventRecord).where(EventRecord.session_id == "s-1"))
        ).scalar_one()
        row = (await s.execute(select(EventRecord).where(EventRecord.id == "e-1"))).scalar_one()
    assert n == 3
    assert row.payload == {"content": "你好"} and row.type == "user_message"


async def test_open_resumes_after_existing_stream(db_session_factory) -> None:
    """恢复语义：新 run 的写者接着旧流的 seq 写，不从 1 重来。"""
    w1 = await EventWriter.open(db_session_factory, "s-2", "r-1", id_factory=_ids("a"))
    await w1.append(EventType.LLM_CALL, {})
    await w1.append(EventType.LLM_CALL, {})
    w2 = await EventWriter.open(db_session_factory, "s-2", "r-2", id_factory=_ids("b"))
    e = await w2.append(EventType.LLM_RESULT, {})
    assert e.seq == 3 and e.run_id == "r-2"


async def test_ghost_write_resolved_by_id_as_success(db_session_factory) -> None:
    """幽灵写入：行已在（上次尝试实际成功），撞约束后按 id 识别为成功，不重复落行。"""
    w = await EventWriter.open(db_session_factory, "s-3", "r-1", id_factory=lambda: "ghost-1")
    async with db_session_factory() as s:
        async with s.begin():
            s.add(
                EventRecord(
                    id="ghost-1",
                    session_id="s-3",
                    run_id="r-1",
                    seq=1,
                    type="llm_call",
                    schema_version=1,
                    payload={},
                )
            )
    e = await w.append(EventType.LLM_CALL, {})
    assert e.seq == 1 and e.id == "ghost-1"
    async with db_session_factory() as s:
        n = (
            await s.execute(select(func.count()).select_from(EventRecord).where(EventRecord.session_id == "s-3"))
        ).scalar_one()
    assert n == 1


async def test_fencing_is_terminal_without_retry(db_session_factory) -> None:
    """围栏信号：seq 被别的写者（不同 id）占用→终态异常，零退避零重试。"""
    slept: list[float] = []
    w = await EventWriter.open(
        db_session_factory, "s-4", "r-1", sleep=_sleep_recorder(slept), id_factory=lambda: "mine-1"
    )
    intruder = await EventWriter.open(db_session_factory, "s-4", "r-9", id_factory=lambda: "other-1")
    await intruder.append(EventType.LLM_CALL, {})
    with pytest.raises(EventWriteFenced, match="s-4"):
        await w.append(EventType.LLM_CALL, {})
    assert slept == []


async def test_transient_failure_retries_then_succeeds(db_session_factory) -> None:
    slept: list[float] = []
    flaky = _FlakyFactory(db_session_factory, fail_times=2)
    w = EventWriter(flaky, "s-5", "r-1", next_seq=1, sleep=_sleep_recorder(slept), id_factory=_ids())
    e = await w.append(EventType.LLM_CALL, {})
    assert e.seq == 1
    assert slept == [0.1, 0.2]


async def test_retry_exhaustion_raises_unavailable(db_session_factory) -> None:
    slept: list[float] = []
    flaky = _FlakyFactory(db_session_factory, fail_times=99)
    w = EventWriter(flaky, "s-6", "r-1", next_seq=1, sleep=_sleep_recorder(slept), id_factory=_ids())
    with pytest.raises(EventStoreUnavailable, match="终止本次 run"):
        await w.append(EventType.LLM_CALL, {})
    assert slept == [0.1, 0.2, 0.4]
    assert flaky.calls == 4  # 1 次初始 + 3 次重试


async def test_os_level_connection_error_retries_like_transient(db_session_factory) -> None:
    """M2.12 停 PG 实录抓出的形状盲区：连接建立期的 OS 级错误未经 SQLAlchemy 包装裸穿。

    asyncpg 建连失败抛的 ConnectionRefusedError 是 OSError 不是 dbapi.Error——SQLAlchemy
    只包装后者，池建连路径的前者会绕过 (OperationalError, InterfaceError) 白名单直接掀翻
    run，违反"退避后明确终止"承诺（00 §6.2 第 6 项）。本测试钉死：OS 级连接错误与包装后的
    连接级故障同待遇——退避重试，恢复即成功（耗尽翻译共享同一分支，已由上一测试覆盖）。
    """
    slept: list[float] = []
    flaky = _FlakyFactory(db_session_factory, fail_times=2, exc=ConnectionRefusedError)
    w = EventWriter(flaky, "s-os1", "r-1", next_seq=1, sleep=_sleep_recorder(slept), id_factory=_ids())
    e = await w.append(EventType.LLM_CALL, {})
    assert e.seq == 1
    assert slept == [0.1, 0.2]


async def test_bug_class_errors_propagate_without_retry(db_session_factory) -> None:
    """白名单哲学：ProgrammingError 是 bug 信号——SQL 写错了重试三次不会试对。"""
    slept: list[float] = []
    flaky = _FlakyFactory(db_session_factory, fail_times=99, exc=ProgrammingError)
    w = EventWriter(flaky, "s-7", "r-1", next_seq=1, sleep=_sleep_recorder(slept), id_factory=_ids())
    with pytest.raises(ProgrammingError):
        await w.append(EventType.LLM_CALL, {})
    assert slept == [] and flaky.calls == 1

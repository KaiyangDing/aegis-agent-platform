"""运行时五表：事件事实源 + 投影 + 会话调度状态（02 §3 / 03 §5，M2.2 交付①）。

events 是状态恢复的唯一事实源；messages / tool_invocations / sessions.summary
是它的投影，在写入事件的同一个 PG 事务内同步派生（写入器随交付②③）。
枚举一律存字符串列 + 代码层 StrEnum 快照守护，不用 PG 原生 ENUM——
加值只改代码不 ALTER TYPE，事件溯源系统的 schema 演进要便宜。
"""

from __future__ import annotations

import asyncio
import os
import socket
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, cast

from sqlalchemy import (
    BigInteger,
    CursorResult,
    DateTime,
    Index,
    Integer,
    Result,
    String,
    Text,
    UniqueConstraint,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from aegis.core.db import Base
from aegis.runtime.events import SCHEMA_VERSION, AgentEvent, EventType


class RunState(StrEnum):
    """sessions.run_state 合法值（02 §3；failed 的进入路径随 M2.10 接电——C9）。"""

    IDLE = "idle"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    FAILED = "failed"


class InvocationStatus(StrEnum):
    """tool_invocations.status：write-ahead 落盘时 running，终局二选一。"""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ApprovalStatus(StrEnum):
    """approvals.status 五态（02 §3：超时与撤回是一等状态；翻转用 CAS——C11）。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class SessionRecord(Base):
    """会话：调度状态（run_state + 租约 + 围栏 + 恢复计数）与 summary 投影的家。"""

    __tablename__ = "sessions"
    __table_args__ = (
        # reaper 的扫描键：租约过期且仍在 running 的会话（03 §5，M2.10 消费）
        Index("ix_sessions_reaper", "run_state", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64))
    run_state: Mapped[str] = mapped_column(String(32), default=RunState.IDLE.value)
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_generation: Mapped[int] = mapped_column(BigInteger, default=0)  # C2 围栏：每次抢租 +1
    recovery_count: Mapped[int] = mapped_column(Integer, default=0)  # C9：超上限置 failed
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # 滚动摘要投影（M2.5 写入）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EventRecord(Base):
    """事件事实源：恢复 / 回放 / 审计的唯一依据；payload 存原文（02 §3）。"""

    __tablename__ = "events"
    __table_args__ = (
        # 并发写入的最后防线：会话锁是第一防线，锁失效（bug/降级）时数据库物理兜底
        UniqueConstraint("session_id", "seq", name="uq_events_session_seq"),
    )

    # 应用侧 uuid：write-ahead 幂等键必须在副作用执行前就存在，自增 id 给不了
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str] = mapped_column(String(64))
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(32))
    schema_version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageRecord(Base):
    """对话原文投影（02 §3）：给"读最近 N 轮"用，不必每次扫全事件流。"""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True)  # 源事件；unique = 投影派生天然防重
    role: Mapped[str] = mapped_column(String(16))  # user / assistant
    content: Mapped[str] = mapped_column(Text)
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ToolInvocationRecord(Base):
    """工具审计投影（02 §3）：result_digest 存摘要，完整原文在 events.payload（X4）。"""

    __tablename__ = "tool_invocations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True)  # = tool_call 事件 id = 幂等键
    tool_name: Mapped[str] = mapped_column(String(64))
    args: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default=InvocationStatus.RUNNING.value)
    result_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalRecord(Base):
    """HITL 审批单。不挂 tool_invocation 外键：03 §4 中审批（③）先于 write-ahead（④），
    审批的是参数快照；event_id 执行后回填审计链（02 §3 已同步此口径）。"""

    __tablename__ = "approvals"
    __table_args__ = (
        # 到期扫描键：pending 且 expires_at 已过（M3.9 reaper 消费）
        Index("ix_approvals_expiry", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 应用侧 uuid：进事件 payload 与审批 API
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)  # M3.9 强制坐席同租户校验
    tool_name: Mapped[str] = mapped_column(String(64))
    args: Mapped[dict[str, Any]] = mapped_column(JSONB)  # 参数快照：批准后前置校验重跑防 TOCTOU
    status: Mapped[str] = mapped_column(String(16), default=ApprovalStatus.PENDING.value)
    operator_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 执行后回填
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


SessionFactory = Callable[[], AsyncSession]
"""写入器眼中的会话工厂：按形状声明（零参可调用、返回 AsyncSession），
不绑死 async_sessionmaker 具体类——测试的故障注入工厂靠这道缝隙进来（与 GatewayLike 同理）。"""
_RETRY_BACKOFF_S: tuple[float, ...] = (0.1, 0.2, 0.4)
"""瞬态故障的退避序列：共 3 次重试（02 §5"短退避重试 3 次"），总额外等待 ~0.7s。
不做抖动：M1 的满抖动防的是多客户端雷群打上游，单写者无此竞争面。"""


class EventStoreUnavailable(RuntimeError):
    """PG 瞬态故障重试耗尽：事实源不可用 = 服务不可用（02 §5），终止本次 run。"""


class EventWriteFenced(RuntimeError):
    """围栏信号（C2）：(session_id, seq) 被别的写者占用——本写者的会话所有权已旁落。
    终态，绝不退避重试；当前 loop 应立即自毁，恢复交给持有新租约的一方。"""


class ProjectionError(RuntimeError):
    """投影派生失败：payload 缺必需字段或被引用的行不存在——bug 信号，裸抛不重试。
    它发生在 append 事务内部，会连事件一起回滚：事实与投影同生共死。"""


def _rowcount(res: Result[Any]) -> int:
    """DML 的 execute 运行时恒返回 CursorResult；存根退化为 Result[Any]——存根缝隙在此单点消化。"""
    return cast(CursorResult[Any], res).rowcount


async def _project_message(s: AsyncSession, r: EventRecord, role: str) -> None:
    s.add(
        MessageRecord(
            session_id=r.session_id,
            event_id=r.id,
            role=role,
            content=r.payload["content"],
            token_usage=r.payload.get("token_usage"),
        )
    )


async def _project_user_message(s: AsyncSession, r: EventRecord) -> None:
    await _project_message(s, r, role="user")


async def _project_assistant_message(s: AsyncSession, r: EventRecord) -> None:
    await _project_message(s, r, role="assistant")


async def _project_tool_call(s: AsyncSession, r: EventRecord) -> None:
    s.add(
        ToolInvocationRecord(
            session_id=r.session_id,
            event_id=r.id,  # = 幂等键：write-ahead 与审计在此对齐
            tool_name=r.payload["tool_name"],
            args=r.payload["args"],
        )
    )


async def _finish_invocation(s: AsyncSession, r: EventRecord, **values: object) -> None:
    res = await s.execute(
        update(ToolInvocationRecord)
        .where(ToolInvocationRecord.event_id == r.payload["tool_call_id"])
        .values(finished_at=func.now(), retry_count=r.payload.get("retry_count", 0), **values)
    )
    if _rowcount(res) != 1:
        raise ProjectionError(f"tool_call_id={r.payload['tool_call_id']} 无对应 invocation 行——write-ahead 顺序被破坏")


async def _project_tool_result(s: AsyncSession, r: EventRecord) -> None:
    await _finish_invocation(
        s,
        r,
        status=InvocationStatus.SUCCEEDED.value,
        result_digest=r.payload.get("digest"),  # 摘要进投影；原文留在事件 payload（X4）
        latency_ms=r.payload.get("latency_ms"),
    )


async def _project_tool_error(s: AsyncSession, r: EventRecord) -> None:
    await _finish_invocation(
        s,
        r,
        status=InvocationStatus.FAILED.value,
        error=r.payload["error"],
        latency_ms=r.payload.get("latency_ms"),
    )


async def _project_summary(s: AsyncSession, r: EventRecord) -> None:
    res = await s.execute(
        update(SessionRecord).where(SessionRecord.id == r.session_id).values(summary=r.payload["summary"])
    )
    if _rowcount(res) != 1:
        raise ProjectionError(f"session={r.session_id} 行不存在——摘要不可能先于会话存在")


_PROJECTORS: dict[str, Callable[[AsyncSession, EventRecord], Awaitable[None]]] = {
    EventType.USER_MESSAGE.value: _project_user_message,
    EventType.ASSISTANT_MESSAGE.value: _project_assistant_message,
    EventType.TOOL_CALL.value: _project_tool_call,
    EventType.TOOL_RESULT.value: _project_tool_result,
    EventType.TOOL_ERROR.value: _project_tool_error,
    EventType.SUMMARY_UPDATED.value: _project_summary,
}
"""投影 dispatch 表：查不到 = 该事件无投影（llm_call/审批类/终止类）。
审批类不在此列不是遗漏——approvals 是独立状态机不是投影（先于事件出生，CAS 随交付④）。"""


async def _apply_projections(s: AsyncSession, record: EventRecord) -> None:
    """投影是事件的纯函数：只读 record，不读时钟与外部状态——回放才可重建。"""
    handler = _PROJECTORS.get(record.type)
    if handler is None:
        return
    try:
        await handler(s, record)
    except KeyError as e:
        raise ProjectionError(f"{record.type} 事件 payload 缺少投影必需字段 {e}") from e


class EventWriter:
    """单写者：一个 run 一个实例，创建前提是已持会话锁（M2.9 接电，约束兜底）。

    append() 返回即事件已 durably committed——write-ahead"落盘是副作用的前置"
    由此成立；append 内部事务是投影同事务派生的挂点（交付③）。
    """

    def __init__(
        self,
        factory: SessionFactory,
        session_id: str,
        run_id: str,
        next_seq: int,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._factory = factory
        self._session_id = session_id
        self._run_id = run_id
        self._next_seq = next_seq
        self._sleep = sleep
        self._id_factory = id_factory or (lambda: uuid.uuid4().hex)

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def run_id(self) -> str:
        return self._run_id

    @classmethod
    async def open(
        cls,
        factory: SessionFactory,
        session_id: str,
        run_id: str,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        id_factory: Callable[[], str] | None = None,
    ) -> EventWriter:
        """读一次流尾接着写——恢复场景下新 run 天然接续旧流的 seq。"""
        async with factory() as s:
            max_seq = (
                await s.execute(
                    select(func.coalesce(func.max(EventRecord.seq), 0)).where(EventRecord.session_id == session_id)
                )
            ).scalar_one()
        return cls(factory, session_id, run_id, max_seq + 1, sleep=sleep, id_factory=id_factory)

    async def append(self, event_type: EventType, payload: Mapping[str, Any]) -> AgentEvent:
        """写一条事实。返回时已 durably committed；seq 仅在成功后推进。"""
        event_id = self._id_factory()
        seq = self._next_seq
        attempt = 0
        while True:
            try:
                async with self._factory() as s:
                    async with s.begin():
                        record = EventRecord(
                            id=event_id,
                            session_id=self._session_id,
                            run_id=self._run_id,
                            seq=seq,
                            type=event_type.value,
                            schema_version=SCHEMA_VERSION,
                            payload=dict(payload),
                        )
                        s.add(record)
                        await _apply_projections(s, record)
                break
            except IntegrityError as e:
                # 三岔口：能抛 IntegrityError 说明 PG 是通的，紧随其后的核查查询几乎必然可用
                if await self._already_written(event_id):
                    break  # 幽灵写入：上次尝试实际成功，commit 的 ack 丢了——当成功
                raise EventWriteFenced(
                    f"session={self._session_id} seq={seq} 已被其他写者占用——所有权旁落，本 loop 应自毁"
                ) from e
            except (OperationalError, InterfaceError) as e:
                # 可重试白名单：连接级故障才配重试；ProgrammingError 等 bug 信号裸抛
                if attempt >= len(_RETRY_BACKOFF_S):
                    raise EventStoreUnavailable(
                        f"事件写入重试 {len(_RETRY_BACKOFF_S)} 次仍失败——事实源不可用，终止本次 run"
                    ) from e
                await self._sleep(_RETRY_BACKOFF_S[attempt])
                attempt += 1
        self._next_seq += 1
        return AgentEvent(
            id=event_id,
            session_id=self._session_id,
            run_id=self._run_id,
            seq=seq,
            type=event_type,
            payload=dict(payload),
        )

    async def _already_written(self, event_id: str) -> bool:
        async with self._factory() as s:
            row = (await s.execute(select(EventRecord.id).where(EventRecord.id == event_id))).scalar_one_or_none()
        return row is not None


class ApprovalStore:
    """审批单状态机的原语层：全部翻转走 CAS（C11）——条件进 WHERE，输赢看 rowcount。

    赢家恰一个：双坐席同点、批准与 reaper 到期扫描赛跑，都由行级原子 UPDATE 裁决，
    输家拿 False/空列表，绝不覆盖赢家。事件写入与 run_state 置位不在此层——
    那是"先取会话锁再恢复"单入口的事（M2.9）；本层只管 approvals 一张表的真相。
    """

    def __init__(self, factory: SessionFactory) -> None:
        self._factory = factory

    async def create(
        self,
        *,
        approval_id: str,
        session_id: str,
        tenant_id: str,
        tool_name: str,
        args: Mapping[str, Any],
        expires_at: datetime,
    ) -> None:
        """开单（status 默认 pending）。调用方是 M2.9 的风险闸门命中路径。"""
        async with self._factory() as s:
            async with s.begin():
                s.add(
                    ApprovalRecord(
                        id=approval_id,
                        session_id=session_id,
                        tenant_id=tenant_id,
                        tool_name=tool_name,
                        args=dict(args),
                        expires_at=expires_at,
                    )
                )

    async def decide(self, approval_id: str, *, approved: bool, operator_id: str) -> bool:
        """坐席决策：pending 且未过期才翻转（C7 fail-closed）——过期单一律拒绝，归宿只有 reaper。

        时钟用 func.now()（DB 时钟）：与 expires_at 的写入时钟同源，无应用侧漂移。
        """
        target = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        async with self._factory() as s:
            async with s.begin():
                res = await s.execute(
                    update(ApprovalRecord)
                    .where(
                        ApprovalRecord.id == approval_id,
                        ApprovalRecord.status == ApprovalStatus.PENDING.value,
                        ApprovalRecord.expires_at > func.now(),
                    )
                    .values(status=target.value, operator_id=operator_id, decided_at=func.now())
                )
        return _rowcount(res) == 1

    async def cancel(self, approval_id: str) -> bool:
        """用户撤回：pending 即可翻转，不查过期——撤回已到期未清扫的单无害且语义更干净。"""
        async with self._factory() as s:
            async with s.begin():
                res = await s.execute(
                    update(ApprovalRecord)
                    .where(
                        ApprovalRecord.id == approval_id,
                        ApprovalRecord.status == ApprovalStatus.PENDING.value,
                    )
                    .values(status=ApprovalStatus.CANCELLED.value, decided_at=func.now())
                )
        return _rowcount(res) == 1

    async def expire_due(self, *, now: datetime | None = None) -> list[str]:
        """把 pending 且已到期的单批量翻 expired，返回翻转的单号（reaper 调度随 M3.9 实装）。

        now 可注入（C7 的可注入时钟）：单测不必等真实时钟走到 expires_at；
        生产不传 → 落回 func.now()，与 decide 同一口钟。
        """
        cutoff = func.now() if now is None else now
        async with self._factory() as s:
            async with s.begin():
                res = await s.execute(
                    update(ApprovalRecord)
                    .where(
                        ApprovalRecord.status == ApprovalStatus.PENDING.value,
                        ApprovalRecord.expires_at <= cutoff,
                    )
                    .values(status=ApprovalStatus.EXPIRED.value, decided_at=func.now())
                    .returning(ApprovalRecord.id)
                )
        return list(res.scalars().all())

    async def attach_event(self, approval_id: str, *, event_id: str) -> bool:
        """执行后回填审计链（ApprovalRecord.event_id"执行后回填"注释与 02 §3 口径兑现，M2.9 D15）。

        CAS：WHERE event_id IS NULL——回填恰一次，重复调用拿 False（C11 同族）。
        """
        async with self._factory() as s:
            async with s.begin():
                res = await s.execute(
                    update(ApprovalRecord)
                    .where(ApprovalRecord.id == approval_id, ApprovalRecord.event_id.is_(None))
                    .values(event_id=event_id)
                )
        return _rowcount(res) == 1


class SessionStateStore:
    """sessions.run_state 的 CAS 原语（C11 同族：条件进 WHERE、输赢看 rowcount）。

    只管一张表的真相；合法迁移图（谁能从哪到哪）见 plans/m2.9 §4.4——T1 idle→running
    （run 启动）/ T2 running→awaiting_approval（挂起）/ T3 awaiting→running（恢复）/
    T4 running→idle（终止）；T5 running→failed 随 M2.10。非法迁移由 expected 参数
    机器拒绝，不存在"直接 SET"的入口。
    """

    def __init__(self, factory: SessionFactory) -> None:
        self._factory = factory

    async def transition(self, session_id: str, *, expected: RunState, to: RunState) -> bool:
        async with self._factory() as s:
            async with s.begin():
                res = await s.execute(
                    update(SessionRecord)
                    .where(SessionRecord.id == session_id, SessionRecord.run_state == expected.value)
                    .values(run_state=to.value)
                )
        return _rowcount(res) == 1


class LeaseLost(RuntimeError):
    """租约旁落（C2 协议一/二）：续租或释放 CAS 打空——所有权已被 reaper 转移。

    终态，绝不退避重试（与 EventWriteFenced 同语义）；当前 loop 立即自毁、
    不再写任何事件，恢复交给持有新租约的一方。
    """


def default_lease_owner() -> str:
    """副本 id（03 §5"lease_owner = 副本 id"）：主机名+pid 在容器多副本与本地进程两形态下唯一且可读。"""
    return f"{socket.gethostname()}:{os.getpid()}"


class LeaseStore:
    """sessions 租约列的 CAS 原语（C2 围栏）。与 ApprovalStore/SessionStateStore 同族：
    条件进 WHERE、输赢看 rowcount/RETURNING；时钟一律 DB 钟 func.now()（now 可注入——C7 先例）。

    全部方法的 SET 不碰 run_state——状态翻转唯一路径是 SessionStateStore.transition
    （m2.9 §4.4 迁移表；reaper 抢租 running→running 不构成翻转）。
    generation 只增不减；(owner, generation) 二元组是一次持有的完整生命周期凭据。
    """

    def __init__(self, factory: SessionFactory) -> None:
        self._factory = factory

    async def acquire(self, session_id: str, *, owner: str, ttl_s: float, now: datetime | None = None) -> int | None:
        """抢租：running 且（无租约 / 已过期 / 租约列 NULL / 同 owner 重入）→ generation +1。

        同 owner 重入（m2.10 偏差 #4）支撑 reaper steal→钩子→resume 的同进程交接；
        None = 活租约在他人手里 / 行非 running / 行不存在（P2 防线保证调用时行存在）。
        """
        cutoff = func.now() if now is None else now
        async with self._factory() as s:
            async with s.begin():
                res = await s.execute(
                    update(SessionRecord)
                    .where(
                        SessionRecord.id == session_id,
                        SessionRecord.run_state == RunState.RUNNING.value,
                        or_(
                            SessionRecord.lease_owner.is_(None),
                            SessionRecord.lease_expires_at.is_(None),
                            SessionRecord.lease_expires_at <= cutoff,
                            SessionRecord.lease_owner == owner,
                        ),
                    )
                    .values(
                        lease_owner=owner,
                        lease_expires_at=cutoff + timedelta(seconds=ttl_s),
                        lease_generation=SessionRecord.lease_generation + 1,
                    )
                    .returning(SessionRecord.lease_generation)
                )
        return res.scalar_one_or_none()

    async def renew(self, session_id: str, *, owner: str, generation: int, ttl_s: float) -> bool:
        """续租心跳：打空即围栏信号（C2 协议二：终态，调用方绝不退避重试）。"""
        async with self._factory() as s:
            async with s.begin():
                res = await s.execute(
                    update(SessionRecord)
                    .where(
                        SessionRecord.id == session_id,
                        SessionRecord.lease_owner == owner,
                        SessionRecord.lease_generation == generation,
                    )
                    .values(lease_expires_at=func.now() + timedelta(seconds=ttl_s))
                )
        return _rowcount(res) == 1

    async def release(self, session_id: str, *, owner: str, generation: int) -> bool:
        """干净收尾：清租约双列 + recovery_count 归零（m2.10 3.2#4：干净收尾证明会话不是毒的）。

        不碰 run_state——终止/挂起的置位由调用方以相邻调用走 SessionStateStore.transition。
        """
        async with self._factory() as s:
            async with s.begin():
                res = await s.execute(
                    update(SessionRecord)
                    .where(
                        SessionRecord.id == session_id,
                        SessionRecord.lease_owner == owner,
                        SessionRecord.lease_generation == generation,
                    )
                    .values(lease_owner=None, lease_expires_at=None, recovery_count=0)
                )
        return _rowcount(res) == 1

    async def steal_expired(
        self, session_id: str, *, owner: str, ttl_s: float, recovery_limit: int, now: datetime | None = None
    ) -> int | None:
        """reaper 抢租：running + 过期（或 NULL 幽灵）+ 未超限 → generation +1 且 recovery_count +1。

        赢家恰一个（两个 reaper 赛跑输家打空拿 None——可能被抢走，也可能已超限，
        由调用方随后 mark_failed 分辨）。
        """
        cutoff = func.now() if now is None else now
        async with self._factory() as s:
            async with s.begin():
                res = await s.execute(
                    update(SessionRecord)
                    .where(
                        SessionRecord.id == session_id,
                        SessionRecord.run_state == RunState.RUNNING.value,
                        or_(
                            SessionRecord.lease_expires_at.is_(None),
                            SessionRecord.lease_expires_at <= cutoff,
                        ),
                        SessionRecord.recovery_count < recovery_limit,
                    )
                    .values(
                        lease_owner=owner,
                        lease_expires_at=cutoff + timedelta(seconds=ttl_s),
                        lease_generation=SessionRecord.lease_generation + 1,
                        recovery_count=SessionRecord.recovery_count + 1,
                    )
                    .returning(SessionRecord.lease_generation)
                )
        return res.scalar_one_or_none()

    async def clear_lease(self, session_id: str) -> None:
        """C9 终局清扫：T5 翻转（SessionStateStore.transition RUNNING→FAILED）的**赢家**随后清租约列。

        恰一次判定权在 transition（状态机 CAS 本就该是判定点，m2.10 偏差 #7）——本方法
        执行时行已 failed、无竞争者，无需 CAS；先翻状态再清列再写审计事件，崩在缝上 =
        failed 带残留租约列/无审计事件（接受，无谎言方向）。
        """
        async with self._factory() as s:
            async with s.begin():
                await s.execute(
                    update(SessionRecord)
                    .where(SessionRecord.id == session_id)
                    .values(lease_owner=None, lease_expires_at=None)
                )

    async def list_expired(self, *, now: datetime | None = None, limit: int = 100) -> list[str]:
        """reaper 扫描（走 ix_sessions_reaper）：running + 过期或 NULL 幽灵（偏差 #5），NULL 最优先。"""
        cutoff = func.now() if now is None else now
        async with self._factory() as s:
            res = await s.execute(
                select(SessionRecord.id)
                .where(
                    SessionRecord.run_state == RunState.RUNNING.value,
                    or_(
                        SessionRecord.lease_expires_at.is_(None),
                        SessionRecord.lease_expires_at <= cutoff,
                    ),
                )
                .order_by(SessionRecord.lease_expires_at.asc().nullsfirst())
                .limit(limit)
            )
        return list(res.scalars().all())

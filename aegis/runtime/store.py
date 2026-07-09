"""运行时五表：事件事实源 + 投影 + 会话调度状态（02 §3 / 03 §5，M2.2 交付①）。

events 是状态恢复的唯一事实源；messages / tool_invocations / sessions.summary
是它的投影，在写入事件的同一个 PG 事务内同步派生（写入器随交付②③）。
枚举一律存字符串列 + 代码层 StrEnum 快照守护，不用 PG 原生 ENUM——
加值只改代码不 ALTER TYPE，事件溯源系统的 schema 演进要便宜。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis.core.db import Base


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

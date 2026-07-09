"""事件类型与 AgentEvent：L2 的"步"级事实单元（03 §5 的运行时侧类型，M2.1 交付③）。

事件即事实源：AgentLoop 每步先写事件再继续，崩溃恢复 = 重放事件重建状态。
本文件只定义运行时侧类型；五表迁移、单写者 seq 分配、同事务投影随 M2.2。
AgentEvent 是"已落盘事实"的镜像——能流出门面的事件必然已有 seq；
不带时间戳：墙钟由 DB 落盘赋值，运行时逻辑不依赖它（确定性回放前提，C31）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = 1
"""当前事件 payload 的 schema 版本。重放器按版本路由解析器（03 §5）：
跨里程碑重构 payload 时版本 +1 并保留旧解析器，老事件永远可重放。"""


class EventType(StrEnum):
    """事件类型全集（03 §5 表，13 类）。值进 events 表与回放断言，快照测试钉死。

    C8 裁决（是否新增 summary_updated）随 M2.2：加成员时快照测试先红，
    显式过口径后再改——防沉默漂移正是快照的用途。
    """

    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    LLM_CALL = "llm_call"
    LLM_RESULT = "llm_result"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_DECIDED = "approval_decided"
    APPROVAL_CANCELLED = "approval_cancelled"
    APPROVAL_EXPIRED = "approval_expired"
    LOOP_TERMINATED = "loop_terminated"
    HANDOFF = "handoff"


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """一条"步"级事实。粒度到步为止——SSE 的逐 token 传输是 M3.10 的通道问题。

    payload 存原文（02 §3 口径，评审 X4：tool_result 完整结果进 payload，
    摘要只进投影表与上下文注入）。seq 由持会话锁的单写者在事务内递增，
    从 1 起；(session_id, seq) 唯一约束是并发写入的最后防线（M2.2）。
    """

    id: str
    session_id: str
    run_id: str
    seq: int
    type: EventType
    payload: Mapping[str, Any]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id 不许为空——事件身份即幂等键，要出境到下游去重（03 §4）")
        if not self.session_id:
            raise ValueError("session_id 不许为空——事件必须归属会话（trace_id ≡ session_id，X5）")
        if not self.run_id:
            raise ValueError("run_id 不许为空——恢复计数与重放边界依赖它（X5/C9）")
        if self.seq < 1:
            raise ValueError(f"seq 须 ≥1（单写者从 1 起递增），得到 {self.seq}")
        if self.schema_version < 1:
            raise ValueError(f"schema_version 须 ≥1，得到 {self.schema_version}")

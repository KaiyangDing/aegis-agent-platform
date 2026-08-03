"""trace 视图装配（M4.1 交付①，00 §8.1）：凭 trace_id ≡ session_id（X5）还原全链路。

自研 trace 而非 OTel 是刻意选择（04 C37）：session=trace、run=root span、
事件=span event——事件流本来就是 trace 源，本模块只做只读装配与出口脱敏，
全程零写入。分层：aegis.obs 与 aegis.apps 同层互不 import——obs 消费
runtime 的 ORM 与 gateway 的账本表，业务层永远不反向依赖 obs。
装配边界：调用方（api 层）负责鉴权并递入已加载的 SessionRecord——
403/404 分工是端点矩阵的事（staff 面 403 点名口径，M3.10 钉死），
装配器不做第二次归属判定。
账本聚合必须包 tenant_context(会话租户)：usage_ledger 在 RLS 名单内，
请求路径 ContextVar 里是**观察者**的租户——admin 跨租查看时二者不同，
不显式覆盖就会静默拿到空账（usage.py admin 跨租视图同款前提）。
耗时口径：
- tool_result/tool_error：直读 payload["latency_ms"]（executor 实测写入，
  投影行 tool_invocations.latency_ms 正是从这里抄的——同源同值，省一次 join）；
- llm_result：与同 run 前一条 llm_call 的 created_at 差（DB 同一报时员；
  半截作废重发时后写的 llm_call 覆盖暂存，配对语义与 D10 一致）；
- 其余事件与配不上对的：null，不猜。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, text

from aegis.core.tenancy import SessionFactory
from aegis.core.tenant_ctx import tenant_context
from aegis.obs.masking import mask_payload
from aegis.runtime.events import EventType
from aegis.runtime.store import EventRecord, SessionRecord


class TraceEvent(BaseModel):
    seq: int
    run_id: str
    type: str
    created_at: datetime
    payload: dict[str, Any]  # 已过 mask_payload——原文只活在 events 表里
    duration_ms: int | None = None


class TraceRun(BaseModel):
    run_id: str
    termination_reason: str | None = None  # 该 run 最后一条 loop_terminated 的 reason
    events: list[TraceEvent]


class TraceUsage(BaseModel):
    requests: int
    prompt_tokens: int
    completion_tokens: int
    cached_hits: int
    cost: Decimal  # pydantic v2 JSON 缺省=精确小数字符串（M3.1"钱不过 float"契约沿用）


class TraceView(BaseModel):
    trace_id: str  # ≡ session_id（X5）：对外词汇是 trace，事实源词汇是会话
    session_id: str
    tenant_id: str
    run_state: str
    runs: list[TraceRun]
    usage: TraceUsage


_USAGE_SQL = text("""
    SELECT count(*)                            AS requests,
           coalesce(sum(prompt_tokens), 0)     AS prompt_tokens,
           coalesce(sum(completion_tokens), 0) AS completion_tokens,
           count(*) FILTER (WHERE cached)      AS cached_hits,
           coalesce(sum(cost), 0)              AS cost
    FROM usage_ledger WHERE session_id = :sid
""")
"""报表聚合用裸 SQL（00 §2.2 数据访问口径）；缓存命中也记账，故 FILTER 可数命中数。"""


class TraceAssembler:
    """从事件流+账本装配一条 trace。只读：全程零写入（关键不变量）。"""

    def __init__(self, factory: SessionFactory) -> None:
        self._factory = factory

    async def assemble(self, session: SessionRecord) -> TraceView:
        async with self._factory() as s:
            rows = (
                await s.execute(
                    select(
                        EventRecord.run_id,
                        EventRecord.seq,
                        EventRecord.type,
                        EventRecord.payload,
                        EventRecord.created_at,
                    )
                    .where(EventRecord.session_id == session.id)
                    .order_by(EventRecord.seq)  # (session_id, seq) 唯一约束的底层索引即查询路径
                )
            ).all()
        runs: dict[str, TraceRun] = {}  # dict 保首现序；run 事实上不交错，但不赖这条前提
        last_llm_call: dict[str, datetime] = {}
        for r in rows:
            run = runs.get(r.run_id)
            if run is None:
                run = runs[r.run_id] = TraceRun(run_id=r.run_id, events=[])
            duration: int | None = None
            if r.type == EventType.LLM_CALL.value:
                last_llm_call[r.run_id] = r.created_at  # 作废重发：后写的 llm_call 覆盖暂存（D10）
            elif r.type == EventType.LLM_RESULT.value:
                started = last_llm_call.pop(r.run_id, None)  # pop=一次配对用掉，杜绝隔步错配
                if started is not None:
                    duration = int((r.created_at - started).total_seconds() * 1000)
            elif r.type in (EventType.TOOL_RESULT.value, EventType.TOOL_ERROR.value):
                latency = r.payload.get("latency_ms")
                duration = latency if isinstance(latency, int) else None
            elif r.type == EventType.LOOP_TERMINATED.value:
                reason = r.payload.get("reason")
                run.termination_reason = reason if isinstance(reason, str) else None
            run.events.append(
                TraceEvent(
                    seq=r.seq,
                    run_id=r.run_id,
                    type=r.type,
                    created_at=r.created_at,
                    payload=mask_payload(r.payload),
                    duration_ms=duration,
                )
            )
        with tenant_context(session.tenant_id):  # 以会话租户身份查账：覆盖观察者上下文（admin 跨租前提）
            async with self._factory() as s:
                usage_row = (await s.execute(_USAGE_SQL, {"sid": session.id})).mappings().one()
        return TraceView(
            trace_id=session.id,
            session_id=session.id,
            tenant_id=session.tenant_id,
            run_state=session.run_state,
            runs=list(runs.values()),
            usage=TraceUsage(
                requests=usage_row["requests"],
                prompt_tokens=usage_row["prompt_tokens"],
                completion_tokens=usage_row["completion_tokens"],
                cached_hits=usage_row["cached_hits"],
                cost=Decimal(usage_row["cost"]),
            ),
        )

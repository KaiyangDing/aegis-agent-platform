"""M4.2 交付①：DB 派生指标族（aegis/obs/metrics.py）——scrape 前刷新的口径测试。

断言纪律两条：带租户/工具名 label 的族用随机 id 过滤式（M2.10 全库扫描教训——
dev 库常驻真实账本行，全局相等断言天生脆）；无 label 维度可过滤的族（cache）
用 delta 式（同测内刷新两次取差）。时序数值零断言（红线 5）。
造数走 EventWriter 真实路径（投影同事务派生）；账本/租户/文档行 ORM 构造。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from aegis.apps.support.rag.models import DocumentRecord
from aegis.core.tenancy import TenantRecord
from aegis.gateway.metering import UsageRecord
from aegis.obs.metrics import REGISTRY, RUNS_TERMINATED, refresh_db_metrics
from aegis.runtime.events import EventType
from aegis.runtime.store import EventWriter, SessionRecord


def _ids() -> tuple[str, str]:
    suffix = uuid4().hex[:8]
    return f"t-mx-{suffix}", f"mx-{suffix}"


def _sample(name: str, labels: dict[str, str]) -> float | None:
    return REGISTRY.get_sample_value(name, labels)


async def _seed_session(factory, tid: str, sid: str) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=sid, tenant_id=tid, user_id="u-mx"))


def _ledger_row(tid: str, sid: str, **kw) -> UsageRecord:
    defaults = dict(
        request_id=f"rq-mx-{uuid4().hex[:8]}",
        tenant_id=tid,
        session_id=sid,
        tier="standard",
        provider="bailian",
        model="m-mx",
        prompt_tokens=0,
        completion_tokens=0,
        cached=False,
        cost=Decimal("0"),
    )
    defaults.update(kw)
    return UsageRecord(**defaults)


async def test_tokens_and_cost_aggregated_from_ledger(db_session_factory) -> None:
    """#5/#6：token 按 (tenant, tier, kind) 双样本、成本按租户——账本 SUM 现算。"""
    tid, sid = _ids()
    async with db_session_factory() as s:
        async with s.begin():
            s.add(_ledger_row(tid, sid, tier="standard", prompt_tokens=100, completion_tokens=40, cost=Decimal("0.02")))
            s.add(_ledger_row(tid, sid, tier="standard", prompt_tokens=50, completion_tokens=10, cost=Decimal("0.01")))
            s.add(_ledger_row(tid, sid, tier="fast", prompt_tokens=7, completion_tokens=3, cost=Decimal("0.001")))
    await refresh_db_metrics(db_session_factory)
    assert _sample("aegis_llm_tokens", {"tenant_id": tid, "tier": "standard", "kind": "prompt"}) == 150
    assert _sample("aegis_llm_tokens", {"tenant_id": tid, "tier": "standard", "kind": "completion"}) == 50
    assert _sample("aegis_llm_tokens", {"tenant_id": tid, "tier": "fast", "kind": "prompt"}) == 7
    cost = _sample("aegis_llm_cost_yuan", {"tenant_id": tid})
    assert cost is not None and abs(cost - 0.031) < 1e-9


async def test_cache_hit_miss_split_delta(db_session_factory) -> None:
    """#9：cached 真假切 hit/miss。无租户 label 可过滤——同测两刷取差（delta 式）。"""
    tid, sid = _ids()
    await refresh_db_metrics(db_session_factory)
    hit_before = _sample("aegis_cache_requests", {"result": "hit"}) or 0.0
    miss_before = _sample("aegis_cache_requests", {"result": "miss"}) or 0.0
    async with db_session_factory() as s:
        async with s.begin():
            s.add(_ledger_row(tid, sid, cached=True))
            s.add(_ledger_row(tid, sid, cached=False))
            s.add(_ledger_row(tid, sid, cached=False))
    await refresh_db_metrics(db_session_factory)
    assert (_sample("aegis_cache_requests", {"result": "hit"}) or 0.0) - hit_before == 1
    assert (_sample("aegis_cache_requests", {"result": "miss"}) or 0.0) - miss_before == 2


async def test_tool_invocations_by_status(db_session_factory) -> None:
    """#7：投影行按 (tool_name, status) 计数——造数走 write-ahead 真实路径。"""
    tid, sid = _ids()
    tool = f"tool-mx-{uuid4().hex[:6]}"
    await _seed_session(db_session_factory, tid, sid)
    w = await EventWriter.open(db_session_factory, sid, "run-mx-1")
    c1 = await w.append(EventType.TOOL_CALL, {"tool_name": tool, "args": {"a": 1}})
    await w.append(EventType.TOOL_RESULT, {"tool_call_id": c1.id, "result": {"ok": True}, "latency_ms": 5})
    await w.append(EventType.TOOL_CALL, {"tool_name": tool, "args": {"a": 2}})  # 无终局=running
    await refresh_db_metrics(db_session_factory)
    assert _sample("aegis_tool_invocations", {"tool_name": tool, "status": "succeeded"}) == 1
    assert _sample("aegis_tool_invocations", {"tool_name": tool, "status": "running"}) == 1


async def test_runs_terminated_joins_tenant(db_session_factory) -> None:
    """#4：events 无 tenant_id 列——租户维度必须 join sessions（计划陷阱 4）。"""
    tid, sid = _ids()
    await _seed_session(db_session_factory, tid, sid)
    w = await EventWriter.open(db_session_factory, sid, "run-mx-1")
    await w.append(EventType.LOOP_TERMINATED, {"reason": "completed", "iteration": 1, "detail": ""})
    await refresh_db_metrics(db_session_factory)
    assert _sample("aegis_runs_terminated", {"tenant_id": tid, "reason": "completed"}) == 1


async def test_handoffs_counted_by_tenant(db_session_factory) -> None:
    """#8：转人工分子（分母用 #4，比率查询侧算——不预计算口径）。"""
    tid, sid = _ids()
    await _seed_session(db_session_factory, tid, sid)
    w = await EventWriter.open(db_session_factory, sid, "run-mx-1")
    await w.append(EventType.HANDOFF, {"reason": "用户要求人工", "ticket_id": "tk-1", "summary": ""})
    await refresh_db_metrics(db_session_factory)
    assert _sample("aegis_handoffs", {"tenant_id": tid}) == 1


async def test_documents_by_status(db_session_factory) -> None:
    """#11（⑫⑱ 观测半）：FAILED/PROCESSING 终于运维可见。"""
    tid, _ = _ids()
    async with db_session_factory() as s:
        async with s.begin():
            s.add(DocumentRecord(id=f"d-mx-{uuid4().hex[:8]}", tenant_id=tid, source="a.md", status="done", meta={}))
            s.add(DocumentRecord(id=f"d-mx-{uuid4().hex[:8]}", tenant_id=tid, source="b.md", status="failed", meta={}))
            s.add(DocumentRecord(id=f"d-mx-{uuid4().hex[:8]}", tenant_id=tid, source="c.md", status="failed", meta={}))
    await refresh_db_metrics(db_session_factory)
    assert _sample("aegis_documents", {"tenant_id": tid, "status": "done"}) == 1
    assert _sample("aegis_documents", {"tenant_id": tid, "status": "failed"}) == 2


async def test_budget_ratio_reuses_month_spend_caliber(db_session_factory) -> None:
    """#10（#23）：ratio=month_spend/预算——复用月度闸门同一实现，cached 行不计入。"""
    tid, sid = _ids()
    async with db_session_factory() as s:
        async with s.begin():
            s.add(TenantRecord(id=tid, name=tid, config={}, token_budget_monthly=1000))
            s.add(_ledger_row(tid, sid, prompt_tokens=400, completion_tokens=200))
            s.add(_ledger_row(tid, sid, prompt_tokens=999, cached=True))  # 缓存回放不花钱，不进分子
    await refresh_db_metrics(db_session_factory)
    ratio = _sample("aegis_tenant_budget_used_ratio", {"tenant_id": tid})
    assert ratio is not None and abs(ratio - 0.6) < 1e-9


async def test_budget_zero_tenant_not_exported(db_session_factory) -> None:
    """#10：budget≤0（闸门关闭）不导出样本——0 预算算比率是除零，也没有告警意义。"""
    tid, sid = _ids()
    async with db_session_factory() as s:
        async with s.begin():
            s.add(TenantRecord(id=tid, name=tid, config={}, token_budget_monthly=0))
            s.add(_ledger_row(tid, sid, prompt_tokens=100))
    await refresh_db_metrics(db_session_factory)
    assert _sample("aegis_tenant_budget_used_ratio", {"tenant_id": tid}) is None


async def test_refresh_db_down_does_not_raise_and_keeps_last(db_session_factory) -> None:
    """fail-safe：工厂炸=全族跳过+留上次值，绝不把异常抛给 scrape（拖垮监控=双倍事故）。"""
    tid, sid = _ids()
    await _seed_session(db_session_factory, tid, sid)
    w = await EventWriter.open(db_session_factory, sid, "run-mx-1")
    await w.append(EventType.LOOP_TERMINATED, {"reason": "completed", "iteration": 1, "detail": ""})
    await refresh_db_metrics(db_session_factory)
    assert _sample("aegis_runs_terminated", {"tenant_id": tid, "reason": "completed"}) == 1

    class _Broken:
        def __call__(self):
            raise RuntimeError("db down")

    await refresh_db_metrics(_Broken())  # 不抛
    assert _sample("aegis_runs_terminated", {"tenant_id": tid, "reason": "completed"}) == 1  # 上次值仍在
    assert RUNS_TERMINATED  # 模块级单例：族声明只发生一次（重复注册陷阱的反面证词）

"""M2.4 交付③：结果规范化——预算收缩、摘要钩子 fail-open、digest、X4 留痕。"""

from __future__ import annotations

import json

from sqlalchemy import select

from aegis.core.tokens import estimate_tokens
from aegis.runtime.executor import OutcomeKind, ToolExecutor
from aegis.runtime.store import EventRecord, EventWriter, ToolInvocationRecord
from aegis.runtime.tools import SideEffect, ToolContext, ToolRegistry, tool

TENANT_CFG = {"approval_threshold": 200}


async def _make(factory, reg: ToolRegistry, sid: str, *, budget: int = 3_000, summarize=None) -> ToolExecutor:
    w = await EventWriter.open(factory, sid, "r-1")
    return ToolExecutor(
        reg,
        w,
        tenant_id="t-a",
        user_id="u-1",
        tenant_config=TENANT_CFG,
        result_token_budget=budget,
        summarize=summarize,
    )


@tool(side_effect=SideEffect.READ)
async def small_read(ctx: ToolContext) -> dict:
    """返回小结果的读工具。"""
    return {"status": "已发货", "eta": "明天"}


@tool(side_effect=SideEffect.READ)
async def big_read(ctx: ToolContext) -> dict:
    """返回超大结果的读工具。"""
    return {"rows": ["订单数据条目内容" * 5 for _ in range(200)]}


@tool(side_effect=SideEffect.READ)
async def multiline_read(ctx: ToolContext) -> dict:
    """返回多行文本的读工具。"""
    return {"text": "第一行\n第二行\n" * 50}


async def _result_event(factory, sid: str) -> EventRecord:
    async with factory() as s:
        return (
            await s.execute(select(EventRecord).where(EventRecord.session_id == sid, EventRecord.type == "tool_result"))
        ).scalar_one()


async def test_small_result_passes_through_with_digest(db_session_factory) -> None:
    """预算内：content 就是序列化原文（可确定重算，payload 不必留 injected）；digest 进投影。"""
    ex = await _make(db_session_factory, ToolRegistry([small_read]), "nm-1")
    out = await ex.execute("small_read", "{}")
    assert out.kind is OutcomeKind.OK
    assert out.content == json.dumps({"status": "已发货", "eta": "明天"}, ensure_ascii=False, default=str)
    row = await _result_event(db_session_factory, "nm-1")
    assert "injected" not in row.payload and "digest" in row.payload
    async with db_session_factory() as s:
        inv = (
            await s.execute(select(ToolInvocationRecord).where(ToolInvocationRecord.event_id == out.tool_call_id))
        ).scalar_one()
    assert inv.result_digest == row.payload["digest"]


async def test_over_budget_uses_summarizer_and_keeps_raw(db_session_factory) -> None:
    """超预算走摘要钩子；X4：原文仍全量在事件流，摘要产物随事件留痕（LLM 产物不可确定重算）。"""

    async def fake_summarize(text: str) -> str:
        return "共 200 条订单数据，全部已发货"

    ex = await _make(db_session_factory, ToolRegistry([big_read]), "nm-2", budget=100, summarize=fake_summarize)
    out = await ex.execute("big_read", "{}")
    assert out.kind is OutcomeKind.OK
    assert "摘要" in out.content and "共 200 条订单数据" in out.content
    row = await _result_event(db_session_factory, "nm-2")
    assert len(row.payload["result"]["rows"]) == 200  # 原文一条不少
    assert row.payload["injected"] == out.content and row.payload["normalization"] == "summary"


async def test_summarizer_failure_fails_open_to_truncation(db_session_factory) -> None:
    """C34：摘要钩子（LLM 增强层）挂了 → fail-open 确定性硬截断 + 留痕审计。"""

    async def broken_summarize(text: str) -> str:
        raise RuntimeError("fast 档挂了")

    ex = await _make(db_session_factory, ToolRegistry([big_read]), "nm-3", budget=100, summarize=broken_summarize)
    out = await ex.execute("big_read", "{}")
    assert out.kind is OutcomeKind.OK and "已截断" in out.content
    assert estimate_tokens(out.content) < 200  # 预算 100 + 截断标注的小额开销
    row = await _result_event(db_session_factory, "nm-3")
    assert row.payload["normalization"] == "truncated"
    assert "fast 档挂了" in row.payload["summarize_error"]


async def test_no_summarizer_truncates_deterministically(db_session_factory) -> None:
    ex = await _make(db_session_factory, ToolRegistry([big_read]), "nm-4", budget=100)
    out = await ex.execute("big_read", "{}")
    assert "已截断" in out.content
    row = await _result_event(db_session_factory, "nm-4")
    assert row.payload["normalization"] == "truncated" and "summarize_error" not in row.payload


async def test_oversized_summary_gets_truncated_too(db_session_factory) -> None:
    """摘要自己超预算也不放行——收缩承诺对产物同样成立。"""

    async def verbose_summarize(text: str) -> str:
        return "长" * 5000

    ex = await _make(db_session_factory, ToolRegistry([big_read]), "nm-5", budget=100, summarize=verbose_summarize)
    out = await ex.execute("big_read", "{}")
    assert "已截断" in out.content and estimate_tokens(out.content) < 200
    row = await _result_event(db_session_factory, "nm-5")
    assert row.payload["normalization"] == "summary"


async def test_digest_is_single_line_and_capped(db_session_factory) -> None:
    ex = await _make(db_session_factory, ToolRegistry([multiline_read]), "nm-6")
    out = await ex.execute("multiline_read", "{}")
    row = await _result_event(db_session_factory, "nm-6")
    digest = row.payload["digest"]
    assert "\n" not in digest and len(digest) <= 200
    assert out.kind is OutcomeKind.OK

"""M3.12② 兜底触发率实测（真实调用；00 §7.2 第 4 条：知识库外 ≥95%，未触发逐条归因）。

分母 = evals/cases.json 里 expectation.kind=out_of_kb 全量（I1：不抄第二份清单）；
路径 = 主 Agent 生产装配直驱（build_agent_spec + 真实检索接线——okb 问题检索空/低分
→ prompt 规则 3 兜底）。**口径限定语**：本口径测 intent 分诊之后的主 Agent 语义，
HANDOFF 直通路径（用户点名转人工）不在分母。
判定 = 三信号并集：回答含兜底信号集（importlib 复用 record_l3_cassettes._FALLBACK_SIGNALS
——evals/README §3 三形态同源）∨ 工具调用含 ticket_create（模型主动开工单转人工）。
未触发条目打印回答**全文**供逐条人工归因——**不承诺 100% 零编造**（00 §7.2 原文，
绝对值是被攻击点）。预算写死：MAX_CALLS=15 / MAX_COST ¥0.20。

    uv run python scripts/fallback_rate_m3.py     # 仓库根执行（.env 相对 cwd）
"""

import asyncio
import importlib.util
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from types import ModuleType

from sqlalchemy import text

from aegis.apps.support.agent import build_agent_spec
from aegis.apps.support.rag.retrieve import RetrievalProvider, Retriever
from aegis.core.db import get_owner_session_factory, get_session_factory
from aegis.core.tenant_ctx import tenant_context
from aegis.gateway.factory import build_embedding_client, build_gateway
from aegis.runtime.runtime import AgentRuntime

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "cases.json"  # M4.4①：seed.jsonl 迁 cases.json（细分类挪 expectation.kind）

MAX_CALLS_BUDGET = 15
MAX_COST_YUAN = Decimal("0.20")
TARGET_RATE = 0.95
RUN_TAG = uuid.uuid4().hex[:8]


def _load_record_script() -> ModuleType:
    """importlib 装载录制脚本（信号集/Trace/_drive/tenant_from_seed 的单一事实源）。

    先注册再执行——该模块含 @dataclass × future-annotations（M3.11 偏差(60) 纪律）。
    """
    spec = importlib.util.spec_from_file_location("record_l3_for_fallback", ROOT / "scripts" / "record_l3_cassettes.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _okb_cases() -> list[dict]:
    rows = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return [r for r in rows if r["expectation"]["kind"] == "out_of_kb"]


async def _spend(session_ids: list[str]) -> tuple[int, Decimal, int]:
    """账本对账走 owner 维护面（D4）：app 引擎在 tenant_context 外读 RLS 表=静默空集
    ——首跑实录 tokens=0、预算护栏盲飞的教训（M3.5 偏差(32) 家族：对账面也算维护面）。"""
    tokens, cost, calls = 0, Decimal("0"), 0
    stmt = text(
        "SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0),"
        " COALESCE(SUM(cost), 0), COUNT(*) FROM usage_ledger WHERE session_id = :sid"
    )
    async with get_owner_session_factory()() as s:
        for sid in session_ids:
            row = (await s.execute(stmt, {"sid": sid})).one()
            tokens += int(row[0])
            cost += Decimal(str(row[1]))
            calls += int(row[2])
    return tokens, cost, calls


async def main() -> None:
    record = _load_record_script()
    seed = record.load_seed()
    cases = _okb_cases()
    if not cases:
        raise SystemExit("cases.json 无 out_of_kb 用例——分母缺失，先查评测集")
    sf = get_session_factory()
    runtime = AgentRuntime(build_gateway(), sf, retrieval=RetrievalProvider(Retriever(sf, build_embedding_client())))

    triggered = 0
    session_ids: list[str] = []
    misses: list[tuple[str, str]] = []
    for case in cases:
        tenant, user = case["tenant_id"], case["user_id"]
        sid = f"fb-{case['id']}-{RUN_TAG}"
        session_ids.append(sid)
        spec = build_agent_spec(record.tenant_from_seed(seed, tenant))
        with tenant_context(tenant):
            await record._ensure_session(sf, sid, tenant, user)
            trace = await record._drive(runtime.run(spec, sid, case["question"]))
        answer = trace.final_answer
        by_signal = any(sig in answer for sig in record._FALLBACK_SIGNALS)
        by_ticket = "ticket_create" in trace.tool_calls
        hit = by_signal or by_ticket
        triggered += int(hit)
        mark = "触发" if hit else "未触发"
        via = "工单转人工" if by_ticket and not by_signal else "兜底话术"
        print(f"[{case['id']}] {mark}（{via if hit else '—'}）  {answer[:60]!r}")
        if not hit:
            misses.append((case["id"], answer))
        tokens, cost, calls = await _spend(session_ids)
        if calls > MAX_CALLS_BUDGET or cost > MAX_COST_YUAN:
            raise SystemExit(f"预算超限（calls={calls}/{MAX_CALLS_BUDGET}，cost=¥{cost}/{MAX_COST_YUAN}）——中止")

    rate = triggered / len(cases)
    verdict = "PASS" if rate >= TARGET_RATE else "未达标——逐条人工归因如下"
    print(f"\n兜底/转人工触发率：{triggered}/{len(cases)} = {rate:.0%}（目标 ≥{TARGET_RATE:.0%}）→ {verdict}")
    for cid, answer in misses:
        print(f"\n[归因 {cid}] 回答全文：\n{answer}")
    tokens, cost, calls = await _spend(session_ids)
    print(f"\n账本实测：tokens={tokens} cost=¥{cost} calls={calls}（上限 {MAX_CALLS_BUDGET}/¥{MAX_COST_YUAN}）")


if __name__ == "__main__":
    asyncio.run(main())

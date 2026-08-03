"""M4.4①：评测双表存取 + 枚举值快照 + 种子幂等（00 §8.1 M4.4 行前半）。

零真实调用；savepoint 世界（conftest create_all 兜底建表，CI 走 alembic——
rag/mock 表测试同款惯例）。断言过滤式（M2.10 全库扫描断言纪律）。
"""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from sqlalchemy import func, select

from aegis.obs.evaluation import EvalCaseRecord, EvalCategory, EvalRunRecord, EvalVerdict

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _seed_script() -> ModuleType:
    """importlib 装载种子脚本（先注册再执行——M3.11 偏差(60) 纪律）。"""
    spec = importlib.util.spec_from_file_location("seed_eval_cases_for_tests", ROOT / "scripts" / "seed_eval_cases.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def test_eval_tables_roundtrip(db_session_factory) -> None:
    """两表写读往返：JSONB expectation 结构保真、cost 走 Decimal（钱不过 float）。"""
    async with db_session_factory() as s:
        async with s.begin():
            s.add(
                EvalCaseRecord(
                    id="case-rt-001",
                    tenant_id="t-rt",
                    user_id="u-rt",
                    category=EvalCategory.ADVERSARIAL.value,
                    question="跨租户探测问题",
                    expectation={"kind": "isolation", "must_not_contain": ["禁词"]},
                )
            )
            s.add(
                EvalRunRecord(
                    batch_id="batch-rt-1",
                    case_id="case-rt-001",
                    verdict=EvalVerdict.PASS.value,
                    score=None,
                    judge_model="qwen3.7-max",
                    cost=Decimal("0.001234"),
                )
            )
    async with db_session_factory() as s:
        case = (await s.execute(select(EvalCaseRecord).where(EvalCaseRecord.id == "case-rt-001"))).scalar_one()
        run = (await s.execute(select(EvalRunRecord).where(EvalRunRecord.case_id == "case-rt-001"))).scalar_one()
    assert case.expectation["must_not_contain"] == ["禁词"]
    assert case.enabled is True and case.source == "seed"  # 列默认值经 DB 往返兑现
    assert run.verdict == "pass" and run.judge_model == "qwen3.7-max"
    assert run.cost == Decimal("0.001234")


def test_category_and_verdict_enum_values() -> None:
    """值快照（防漂移）：三类用例与三态判定——改枚举=改评测口径，先过拍板再改这里。"""
    assert {c.value for c in EvalCategory} == {"retrieval", "e2e", "adversarial"}
    assert {v.value for v in EvalVerdict} == {"pass", "fail", "error"}


async def test_seed_script_idempotent(db_session_factory) -> None:
    """种子幂等：同 JSON 跑两遍行数不变；字段修订重跑更新生效且 enabled 不被冲掉。"""
    script = _seed_script()
    rows = script.load_cases()
    ids = [r["id"] for r in rows]

    ins1, upd1 = await script.seed_cases(db_session_factory, rows)
    assert ins1 + upd1 == len(rows)

    async def _count() -> int:
        async with db_session_factory() as s:
            return int((await s.execute(select(func.count()).where(EvalCaseRecord.id.in_(ids)))).scalar_one())

    assert await _count() == len(rows)
    # 手工关停一条（运营开关）+ 修订一条 question 后重跑：更新生效、enabled 保留、行数不变
    async with db_session_factory() as s:
        async with s.begin():
            target = (await s.execute(select(EvalCaseRecord).where(EvalCaseRecord.id == ids[0]))).scalar_one()
            target.enabled = False
    revised = [dict(r) for r in rows]
    revised[0] = {**revised[0], "question": revised[0]["question"] + "（修订）"}
    ins2, upd2 = await script.seed_cases(db_session_factory, revised)
    assert (ins2, upd2) == (0, len(rows))
    async with db_session_factory() as s:
        row0 = (await s.execute(select(EvalCaseRecord).where(EvalCaseRecord.id == ids[0]))).scalar_one()
    assert row0.question.endswith("（修订）")
    assert row0.enabled is False  # 重跑种子不许冲掉运营开关
    assert await _count() == len(rows)

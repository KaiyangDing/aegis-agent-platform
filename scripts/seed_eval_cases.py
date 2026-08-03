"""评测用例种子：evals/cases.json（定义源，PR 可审）→ eval_cases 表（运行事实源）。

幂等 upsert（M4.4 §3-1）：同 id 撞行走 DO UPDATE——重跑无副作用、字段修订生效；
**enabled 与 created_at 不在更新列**：enabled 是运营开关（临时收窄控费批次的手工
UPDATE 不许被重跑种子冲掉），created_at 是首次登记时刻。
走 owner 维护面（D4：种子/维护/对账三类平台视角显式声明——eval_cases 在 RLS
名单内，app 引擎无上下文写入必被 WITH CHECK 拒）。

    uv run python scripts/seed_eval_cases.py     # 仓库根执行（.env 相对 cwd）
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from aegis.core.db import get_owner_session_factory
from aegis.core.tenancy import SessionFactory
from aegis.obs.evaluation import EvalCaseRecord

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "cases.json"


def load_cases() -> list[dict[str, Any]]:
    rows = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    assert isinstance(rows, list) and rows, "cases.json 为空或不是数组"
    return rows


async def seed_cases(factory: SessionFactory, rows: list[dict[str, Any]]) -> tuple[int, int]:
    """upsert 全量用例，返回 (新插入数, 更新数)。函数级注入 factory——测试用
    savepoint 工厂、生产用 owner 工厂，同一实现（脚本可测性纪律）。"""
    ids = [r["id"] for r in rows]
    async with factory() as s:
        async with s.begin():
            existing = set(
                (await s.execute(select(EvalCaseRecord.id).where(EvalCaseRecord.id.in_(ids)))).scalars().all()
            )
            for row in rows:
                stmt = pg_insert(EvalCaseRecord).values(
                    id=row["id"],
                    tenant_id=row["tenant_id"],
                    user_id=row["user_id"],
                    category=row["category"],
                    question=row["question"],
                    expectation=row["expectation"],
                    source=row.get("source", "seed"),
                )
                await s.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["id"],
                        set_={
                            "tenant_id": stmt.excluded.tenant_id,
                            "user_id": stmt.excluded.user_id,
                            "category": stmt.excluded.category,
                            "question": stmt.excluded.question,
                            "expectation": stmt.excluded.expectation,
                            "source": stmt.excluded.source,
                        },
                    )
                )
    inserted = len(ids) - len(existing)
    return inserted, len(existing)


async def main() -> None:
    rows = load_cases()
    inserted, updated = await seed_cases(get_owner_session_factory(), rows)
    print(f"eval_cases 种子完成：共 {len(rows)} 条（新插入 {inserted}，更新 {updated}）")


if __name__ == "__main__":
    asyncio.run(main())

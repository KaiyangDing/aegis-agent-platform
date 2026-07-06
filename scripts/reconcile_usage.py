"""对账脚本：usage_ledger 四维聚合（租户/模型/天/会话）——M1 验收第 4 条。

报表属于"复杂聚合"档：按 ORM 课的分工立场直接写裸 SQL（text），一层不糊。

    uv run python scripts/reconcile_usage.py
"""

import asyncio

from sqlalchemy import text

from aegis.core.db import get_session_factory

QUERIES = {
    "按租户": """
        SELECT tenant_id,
               count(*)                                   AS calls,
               sum(prompt_tokens + completion_tokens)     AS tokens,
               round(sum(cost), 4)                        AS cost_yuan,
               count(*) FILTER (WHERE cached)             AS cache_hits
        FROM usage_ledger GROUP BY tenant_id ORDER BY cost_yuan DESC""",
    "按模型": """
        SELECT model, count(*) AS calls,
               sum(prompt_tokens + completion_tokens) AS tokens,
               round(sum(cost), 4) AS cost_yuan
        FROM usage_ledger GROUP BY model ORDER BY cost_yuan DESC""",
    "按天": """
        SELECT date_trunc('day', created_at)::date AS day, count(*) AS calls,
               sum(prompt_tokens + completion_tokens) AS tokens,
               round(sum(cost), 4) AS cost_yuan
        FROM usage_ledger GROUP BY 1 ORDER BY 1""",
    "按会话 Top10": """
        SELECT coalesce(session_id, '-') AS session, tenant_id,
               count(*) AS calls, round(sum(cost), 4) AS cost_yuan
        FROM usage_ledger GROUP BY 1, 2 ORDER BY cost_yuan DESC LIMIT 10""",
}


async def main() -> None:
    async with get_session_factory()() as session:
        for title, query in QUERIES.items():
            rows = (await session.execute(text(query))).all()
            print(f"\n== {title} ==")
            if not rows:
                print("  (空)")
                continue
            for row in rows:
                print("  " + " | ".join(str(v) for v in row))


if __name__ == "__main__":
    asyncio.run(main())

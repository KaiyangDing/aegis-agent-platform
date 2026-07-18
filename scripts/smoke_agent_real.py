"""M2.12 真实冒烟：M2 第二处也是最后一处真实调用（00 §6.0 例外②），只断不变量。

口径（写死，凭证照抄）：真实调用 ×1 会话、standard 档（模型池 v3 首选 qwen-plus）、
预算三道写死（P1 拍板：max_iterations=4 / session_token_budget=8_000 / 成本顶 ¥0.10）；
只断三条不变量（无重复副作用 / seq 连续合法 / 合法终止）+ 成本顶，绝不断言回答文本
（真实模型输出非确定，断文本=断质量，越界——00 §6.2 第 3 项）。

    uv run python scripts/smoke_agent_real.py     # 仓库根执行；需 PG/Redis 在跑、.env 有 key

预计 <60s、成本 ~¥0.005（凭证以账本为准）。
"""

from __future__ import annotations

import asyncio
import os
import uuid
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from aegis.core.config import get_settings
from aegis.core.db import get_session_factory
from aegis.gateway.factory import build_gateway
from aegis.runtime.events import EventType
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec, LoopPolicy, TerminationReason
from aegis.runtime.store import SessionRecord
from aegis.runtime.tools import SideEffect, ToolContext, tool

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "m2_real_smoke.txt"
SESSION_ID = f"smoke-{uuid.uuid4().hex[:12]}"
TENANT_ID = "smoke"
USER_ID = "smoke-user"

# P1 拍板（2026-07-17）：预算三道写死。循环侧两道打到即"合法终止"不算失败；
# 成本顶走账本实测对账（C25 账单侧），超顶 exit 1
MAX_ITERATIONS = 4
SESSION_TOKEN_BUDGET = 8_000
COST_CAP_CNY = Decimal("0.10")

EXECUTED: list[str] = []
"""写工具的下游视角：收到的幂等键序列——不变量①"无重复副作用"的第一证据。"""


@tool(side_effect=SideEffect.READ)
async def order_query(ctx: ToolContext, order_id: str) -> dict:
    """查询订单状态（冒烟自足假数据——脚本不 import tests/，包边界纪律）。"""
    return {"order_id": order_id, "status": "已发货", "eta": "明天 18:00 前"}


@tool(side_effect=SideEffect.WRITE, risk_exempt=True)
async def ticket_create(ctx: ToolContext, title: str) -> dict:
    """创建工单（低危写显式豁免——真实调用下挂起会悬死脚本，HITL 已由回放路径覆盖）。"""
    EXECUTED.append(ctx.tool_call_id)
    return {"ticket_id": f"TK-{len(EXECUTED)}", "title": title}


SPEC = AgentSpec(
    system_prompt=(
        "你是云杉电商·数码商城的在线客服助手。处理用户请求时：先调用 order_query 查询订单，"
        "再调用 ticket_create 创建跟进工单，最后用一两句话向用户总结。回答保持简洁。"
    ),
    tools=(order_query, ticket_create),
    policy=LoopPolicy(max_iterations=MAX_ITERATIONS, session_token_budget=SESSION_TOKEN_BUDGET),
    model_tier="standard",
)
USER_INPUT = "帮我查一下订单 SMK-20260718-001 到哪了，顺便建一条名为「烟测跟进」的工单。"


async def main() -> None:
    # 冒烟必须是真实调用：固定 prompt 第二跑会命中精确缓存（零成本假调用），关掉消除类别（D9 同款）
    os.environ["CACHE_TTL_SECONDS"] = "0"
    if not get_settings().dashscope_api_key.get_secret_value():
        raise SystemExit("DASHSCOPE_API_KEY 为空——请在仓库根运行（.env 相对 cwd）")
    sf = get_session_factory()
    async with sf() as s:
        async with s.begin():
            s.add(SessionRecord(id=SESSION_ID, tenant_id=TENANT_ID, user_id=USER_ID))  # P2：无行拒绝起跑
    runtime = AgentRuntime(build_gateway(), sf)
    print(
        f"冒烟会话 {SESSION_ID}（standard 档；预算 {MAX_ITERATIONS} 轮 / {SESSION_TOKEN_BUDGET} est / ¥{COST_CAP_CNY}）"
    )
    types: list[str] = []
    reason = ""
    async for ev in runtime.run(SPEC, SESSION_ID, USER_INPUT):
        types.append(ev.type.value)
        print(f"  seq={ev.seq:2d}  {ev.type.value}")
        if ev.type is EventType.LOOP_TERMINATED:
            reason = ev.payload["reason"]

    async with sf() as s:
        orphan = (
            await s.execute(
                text(
                    "SELECT COUNT(*) FROM events e LEFT JOIN tool_invocations ti ON ti.event_id = e.id "
                    "WHERE e.session_id = :sid AND e.type = 'tool_call' AND ti.id IS NULL"
                ),
                {"sid": SESSION_ID},
            )
        ).scalar_one()
        dupes = (
            await s.execute(
                text(
                    "SELECT COUNT(*) FROM (SELECT event_id FROM tool_invocations WHERE session_id = :sid "
                    "GROUP BY event_id HAVING COUNT(*) > 1) d"
                ),
                {"sid": SESSION_ID},
            )
        ).scalar_one()
        seqs = [
            r[0]
            for r in (
                await s.execute(
                    text("SELECT seq FROM events WHERE session_id = :sid ORDER BY seq"), {"sid": SESSION_ID}
                )
            ).all()
        ]
        cost = Decimal(
            str(
                (
                    await s.execute(
                        text("SELECT COALESCE(SUM(cost), 0) FROM usage_ledger WHERE session_id = :sid"),
                        {"sid": SESSION_ID},
                    )
                ).scalar_one()
            )
        )
        models = [
            r[0]
            for r in (
                await s.execute(
                    text("SELECT DISTINCT model FROM usage_ledger WHERE session_id = :sid ORDER BY model"),
                    {"sid": SESSION_ID},
                )
            ).all()
        ]

    failures: list[str] = []
    if len(EXECUTED) != len(set(EXECUTED)):
        failures.append(f"不变量① 下游幂等键重复：{EXECUTED}")
    if orphan:
        failures.append(f"不变量① tool_call 事件缺审计投影 {orphan} 行")
    if dupes:
        failures.append(f"不变量① 幂等键在 tool_invocations 重复 {dupes} 组")
    if seqs != list(range(1, len(seqs) + 1)):
        failures.append(f"不变量② seq 不连续：{seqs}")
    legal = {r.value for r in TerminationReason} - {TerminationReason.GATEWAY_REJECTED.value}
    if not types or types[-1] != "loop_terminated" or reason not in legal:
        failures.append(f"不变量③ 终止不合法：末事件={types[-1] if types else '无'}，reason={reason!r}")
    if cost > COST_CAP_CNY:
        failures.append(f"成本超顶：¥{cost} > ¥{COST_CAP_CNY}")
    if failures:
        print("冒烟失败（不落盘凭证）：")
        for item in failures:
            print(f"  - {item}")
        raise SystemExit(1)

    lines = [
        "M2.12 真实冒烟凭证（真实调用例外②——M2 最后一处；只断不变量，不断回答文本）",
        f"session_id：{SESSION_ID}；档位 standard；事件 {len(seqs)} 条；账本模型：{models}",
        f"事件类型序列：{types}",
        f"不变量① 无重复副作用：下游幂等键 {len(EXECUTED)} 把零重复；孤儿 tool_call=0；键重复组=0",
        f"不变量② seq 连续合法：1..{len(seqs)} 无空洞",
        f"不变量③ 合法终止：reason={reason}（合法集=TerminationReason 去 gateway_rejected）",
        f"成本（账本实测）：¥{cost} ≤ 顶 ¥{COST_CAP_CNY}（预算三道写死本脚本）",
        "口径注记：CACHE_TTL_SECONDS=0 防缓存命中冒充真实调用；00 §6.2 第 7 项结构保证——",
        "  真实调用只存在于 scripts/（本脚本与 record_long_dialog.py），tests/ 全 FakeGateway，",
        "  CI 工作流无 DASHSCOPE_API_KEY 注入。",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"三不变量 PASS，成本 ¥{cost}。凭证已落盘：{REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

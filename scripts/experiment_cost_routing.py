"""M4.6 实验①：档位路由降本对照（真实调用；00 §8.1 M4.6 行、plans/m4 第七章）。

三组同题对照（80 条全唯一，evals/cost_questions.json routing 节，lint 钉死）：
  A  基线1 = 全部强制 strong 档——「不做分档的保守实现」：无意图层，每题直进主 Agent；
  A' 基线2 = 全部强制 standard 档——「不做分档的朴素实现」，驱动形态同 A；
  B  实验组 = 正常分诊路由（ChatService 生产编排：fast 分类 → FAQ 直答 fast /
     HANDOFF 直通零 LLM / 其余主 Agent standard）——分诊自身的 fast 调用诚实入账。
降本% = (cost_基线 − cost_B) / cost_基线，报 vs-strong 与 vs-standard 两个数字，
不预设目标值（04 M4）。

口径要点（报告 §1 同文）：
- 缓存关闭（进程 env CACHE_TTL_SECONDS=0 → gateway cache=None）=唯一集的第二道保险；
  故障注入显式归零（不赌 .env 干净），两项装配后有断言核验（门要先验过才算响）；
- 实验租户 exp-route 的 token_budget_monthly=0=预算闸关闭（#22），防 BudgetExceeded 混入；
- 每题一个新会话；组间按精确 sid 清单分账（P3 拍板；M4.4④ LIKE 跨批撞账后的对账正解），
  聚合 SQL 与 sid 清单全文进报告=数字可从 ledger 复算；
- 全程 tenant_context(exp-route) 包驱动（00 §2.2 (58) 配对纪律）——计量 fail-open 会静默
  丢账，故每组收尾做「账本 sid 覆盖数=驱动数」sanity，缺账即中止不出报告（凭证不掺假）；
- 检索/种子的 embedding 行不计入对照数字（tier<>'embedding' 过滤），另账单列；
- 预算硬上限 settings.cost_routing_token_budget（00 §8.0 写死在配置），超限中止落 partial。

用法（仓库根执行；PG/Redis 在跑、迁移与 .env DASHSCOPE key 就位）：
    uv run python scripts/experiment_cost_routing.py --smoke   # 每组 2 题连通冒烟，不写报告
    uv run python scripts/experiment_cost_routing.py           # 完整 80 题×3 组 → reports/m4_cost_routing.txt
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import sys
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

from sqlalchemy import text

# aegis 导入不触发 Settings 实例化（get_settings 是惰性 lru_cache）——
# 控制变量 env 在 main() 首行、任何 get_settings() 消费之前落地。
from aegis.apps.support.agent import build_agent_spec
from aegis.apps.support.rag.retrieve import RetrievalProvider, Retriever
from aegis.apps.support.revalidate import build_precheck
from aegis.apps.support.service import ChatService
from aegis.core.config import get_settings
from aegis.core.db import get_owner_session_factory, get_session_factory
from aegis.core.tenancy import TenantDirectory, TenantRecord
from aegis.core.tenant_ctx import tenant_context
from aegis.gateway.factory import build_embedding_client, build_gateway
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.store import SessionRecord

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "m4_cost_routing.txt"

# (组键, 报告口径一句话)；组键进 sid——三组定义是报告 §1 的正文
GROUPS: tuple[tuple[str, str], ...] = (
    ("strong", "A=基线1：全部强制 strong 档（不做分档的保守实现，无意图层直进主 Agent）"),
    ("standard", "A'=基线2：全部强制 standard 档（不做分档的朴素实现，驱动形态同 A）"),
    ("tiered", "B=实验组：正常分诊路由（fast 分类 + FAQ 直答 fast + 主 Agent standard）"),
)

_AGG_SQL = (
    "SELECT count(*) AS calls, count(*) FILTER (WHERE cached) AS cached_calls, "
    "coalesce(sum(prompt_tokens), 0) AS p, coalesce(sum(completion_tokens), 0) AS c, "
    "coalesce(sum(cost), 0) AS cost "
    "FROM usage_ledger WHERE session_id = ANY(:sids) AND tier <> 'embedding'"
)
_TIER_SQL = (
    "SELECT tier, model, count(*) AS calls, coalesce(sum(prompt_tokens), 0) AS p, "
    "coalesce(sum(completion_tokens), 0) AS c, coalesce(sum(cost), 0) AS cost "
    "FROM usage_ledger WHERE session_id = ANY(:sids) AND tier <> 'embedding' "
    "GROUP BY tier, model ORDER BY tier, model"
)
_COVERAGE_SQL = (
    "SELECT count(DISTINCT session_id) FROM usage_ledger WHERE session_id = ANY(:sids) AND tier <> 'embedding'"
)
_SID_TOKENS_SQL = (
    "SELECT coalesce(sum(prompt_tokens + completion_tokens), 0) "
    "FROM usage_ledger WHERE session_id = :sid AND tier <> 'embedding'"
)
_EMBED_SQL = (
    "SELECT count(*), coalesce(sum(prompt_tokens), 0), coalesce(sum(cost), 0) "
    "FROM usage_ledger WHERE tenant_id = :tid AND tier = 'embedding' AND id > :floor"
)


def _load_script(stem: str, alias: str) -> ModuleType:
    """importlib 装载兄弟脚本（scripts 非包；run_eval._record_l3 同款惯用法）。"""
    path = ROOT / "scripts" / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(alias, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # 装载纪律：先注册再执行（M3.11 教训⑵）
    spec.loader.exec_module(module)
    return module


@dataclass
class GroupResult:
    key: str
    caption: str
    sids: list[str] = field(default_factory=list)
    driven: int = 0
    errored: list[str] = field(default_factory=list)


async def main() -> None:
    # 控制变量先于任何 get_settings() 消费落 env；cache_clear 防御「已被谁先唤醒」。
    os.environ["CACHE_TTL_SECONDS"] = "0"
    os.environ["FAULT_INJECTION_RATE"] = "0.0"

    parser = argparse.ArgumentParser(description="M4.6 实验①：档位路由降本")
    parser.add_argument("--smoke", action="store_true", help="每组只跑前 2 题，不写报告")
    args = parser.parse_args()

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.cache_ttl_seconds == 0, "控制变量未生效：缓存必须关闭（实验①口径）"
    assert settings.fault_injection_rate == 0.0, "控制变量未生效：故障注入必须关闭"
    budget = settings.cost_routing_token_budget

    common = _load_script("cost_common", "cost_common_for_routing")
    seed = _load_script("seed_demo", "seed_demo_for_routing")
    tid: str = common.ROUTE_TENANT_ID
    uid: str = common.ROUTE_USER_ID
    questions: list[dict[str, str]] = common.load_questions()["routing"]
    if args.smoke:
        # 冒烟面刻意异质：1 条 FAQ（B 走直答）+ 1 条工具题（B 走主 Agent+mock 通路）
        questions = [questions[0], next(q for q in questions if q["kind"] == "tool")]

    owner = get_owner_session_factory()
    sf = get_session_factory()
    gateway = build_gateway()
    runtime = AgentRuntime(
        gateway, sf, retrieval=RetrievalProvider(Retriever(sf, build_embedding_client())), precheck=build_precheck(sf)
    )
    service = ChatService(
        gateway=gateway, factory=sf, directory=TenantDirectory(sf), runtime=runtime, lock=None, redis=None
    )

    async def ensure_session(sid: str) -> None:
        async with sf() as s:
            async with s.begin():
                s.add(SessionRecord(id=sid, tenant_id=tid, user_id=uid))

    async def sid_tokens(sid: str) -> int:
        async with owner() as s:
            return int((await s.execute(text(_SID_TOKENS_SQL), {"sid": sid})).scalar_one())

    # ---- 种子（幂等）：租户/用户/只读订单 + 语料摄取（embedding 属 setup 另账）----
    async with owner() as s:
        embed_floor = int((await s.execute(text("SELECT coalesce(max(id), 0) FROM usage_ledger"))).scalar_one())
    await seed.seed_tenants_users(
        owner,
        tenants=[t for t in common.EXP_TENANTS if t["id"] == tid],
        users=[u for u in common.EXP_USERS if u["tenant_id"] == tid],
    )
    await seed.seed_orders(owner, orders=[o for o in common.EXP_ORDERS if o["tenant_id"] == tid])
    with tenant_context(tid):
        fresh, resumed, skipped = await seed.seed_corpus_for_tenant(
            sf, build_embedding_client(), tenant_id=tid, corpus_dir=common.EXP_CORPUS_DIR
        )
    print(f"[种子] exp-route 语料：新摄取 {fresh} 续传 {resumed} 跳过 {skipped}（跳过=幂等省钱闸）")

    # ---- 三组驱动（顺序：A → A' → B；预算全局累计，超限即停）----
    tenant_row: dict[str, Any] = next(t for t in common.EXP_TENANTS if t["id"] == tid)
    tenant = TenantRecord(
        id=tenant_row["id"],
        name=tenant_row["name"],
        config=dict(tenant_row["config"]),
        token_budget_monthly=tenant_row["token_budget_monthly"],
    )
    base_spec = build_agent_spec(tenant)
    specs = {"strong": replace(base_spec, model_tier="strong"), "standard": replace(base_spec, model_tier="standard")}

    run_tag = uuid4().hex[:8]
    started_at = datetime.now(UTC)
    spent = 0
    partial = False
    results: list[GroupResult] = []
    for key, caption in GROUPS:
        result = GroupResult(key, caption)
        results.append(result)
        for row in questions:
            if spent >= budget:
                partial = True
                break
            sid = f"cost-route-{key}-{row['id']}-{run_tag}"
            try:
                with tenant_context(tid):
                    await ensure_session(sid)
                    if key == "tiered":
                        async for _ in service.handle(
                            tenant_id=tid, user_id=uid, session_id=sid, message=row["question"]
                        ):
                            pass
                    else:
                        async for _ in runtime.run(specs[key], sid, row["question"]):
                            pass
            except Exception as e:  # 单题失败不拖垮批次：如实记 errored，报告里点名
                result.errored.append(row["id"])
                print(f"[{key}] {row['id']} 异常：{type(e).__name__}: {e}")
            result.sids.append(sid)
            result.driven += 1
            delta = await sid_tokens(sid)
            spent += delta
            print(f"[{key}] {row['id']} 完成，token {delta}，累计 {spent}/{budget}")
        if partial:
            print(f"[预算] 累计 {spent} ≥ {budget}，中止批次（{key} 组止于 {result.driven}/{len(questions)}）")
            break

    # ---- 对账 sanity：每组账本 sid 覆盖数必须=驱动数（计量 fail-open 掉账即中止）----
    async with owner() as s:
        for result in results:
            covered = int((await s.execute(text(_COVERAGE_SQL), {"sids": result.sids})).scalar_one())
            expect = result.driven - len(result.errored)  # errored 题可能零账行，不计入覆盖义务
            if covered < expect:
                raise SystemExit(f"[{result.key}] 账本覆盖 {covered}/{expect}——计量掉账（(58) 面），中止不出报告")
            print(f"[对账] {result.key}: sid 覆盖 {covered}/{expect} OK")

    # ---- 聚合与报告 ----
    async with owner() as s:
        agg: dict[str, Any] = {}
        tiers: dict[str, list[Any]] = {}
        for result in results:
            agg[result.key] = (await s.execute(text(_AGG_SQL), {"sids": result.sids})).one()
            tiers[result.key] = list((await s.execute(text(_TIER_SQL), {"sids": result.sids})).all())
        embed_row = (await s.execute(text(_EMBED_SQL), {"tid": tid, "floor": embed_floor})).one()

    for result in results:
        row = agg[result.key]
        print(
            f"[{result.key}] 调用 {row.calls}（cached {row.cached_calls}）"
            f" prompt {row.p} completion {row.c} cost ¥{row.cost}"
        )
    if args.smoke:
        print("[冒烟] 通过：管线连通、账本覆盖齐。正式跑批不带 --smoke。")
        return
    if partial:
        print("[partial] 预算中止：组间不可比，本次不计算降本%，报告标记 partial。")

    def pct(base: Decimal, exp: Decimal) -> str:
        return f"{(base - exp) / base * 100:.1f}%" if base else "n/a"

    lines: list[str] = []
    stamp = started_at.strftime("%Y-%m-%d %H:%M:%SZ")
    done_stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    lines.append(f"M4.6 实验①：档位路由降本（执行 {stamp} → {done_stamp}，run_tag={run_tag}）")
    lines.append("=" * 72)
    lines.append("1. 实验口径")
    lines.append("- 问题集：evals/cost_questions.json routing 节，80 条全唯一（不受重复率污染，")
    lines.append("  节内/节间/与评测集零交集由 tests/obs/test_cost_traffic.py 钉死）；")
    lines.append("  意图分布为声明性假设：FAQ 30%(24)/RAG 40%(32)/工具 20%(16)/闲聊 10%(8)，")
    lines.append("  贴近客服流量构成；工具题只读（order_query/logistics_query），写路径不在实验面；")
    lines.append("- 控制变量：精确缓存关闭（CACHE_TTL_SECONDS=0，装配后断言核验）；故障注入 0；")
    lines.append("  实验租户 exp-route 月度预算闸关闭（token_budget_monthly=0）；数据面=tenant-a 镜像")
    lines.append("  （同名/同 faq digest/语料同源 data/corpus/tenant-a/只读订单 EXPR-1001..1008）；")
    lines.append("- 组别定义（三组同题同序，每题一个新会话，进程内直驱与生产同栈层）：")
    for _, caption in GROUPS:
        lines.append(f"    {caption}")
    lines.append("- 分账：组间精确 sid 清单（见附录），全部数字可由 usage_ledger 复算；")
    lines.append("  检索查询向量与语料种子的 embedding 行不计入对照数字，另账单列；")
    lines.append(f"- 预算：cost_routing_token_budget={budget}（超限中止落 partial）。")
    lines.append("")
    lines.append("2. 原始数字（usage_ledger 聚合，tier<>'embedding'）")
    for result in results:
        row = agg[result.key]
        note = f"；errored {len(result.errored)}：{result.errored}" if result.errored else ""
        lines.append(
            f"- {result.key}: 题数 {result.driven}/{len(questions)}，LLM 调用 {row.calls}，"
            f"prompt {row.p}，completion {row.c}，cost ¥{row.cost}{note}"
        )
        for t in tiers[result.key]:
            lines.append(f"    {t.tier}/{t.model}: 调用 {t.calls}，prompt {t.p}，completion {t.c}，cost ¥{t.cost}")
    lines.append(
        f"- embedding 另账（setup 语料种子+三组检索查询向量）：{embed_row[0]} 行，{embed_row[1]} token，¥{embed_row[2]}"
    )
    lines.append("")
    lines.append("3. 结果")
    if partial:
        lines.append("- partial：预算中止，组间不可比，本次不计算降本%（诚实缺席）。")
    else:
        cost = {r.key: Decimal(agg[r.key].cost) for r in results}
        lines.append(f"- 档位路由降本 vs-strong  ：{pct(cost['strong'], cost['tiered'])}（A→B，同题 80 条）")
        lines.append(f"- 档位路由降本 vs-standard：{pct(cost['standard'], cost['tiered'])}（A'→B，同题 80 条）")
        lines.append("- 限定语：数字只在「本问题集构成 + 本价目表 + 缓存关闭」口径下成立；")
        lines.append("  B 组成本已诚实计入 fast 分诊调用与检索开销外的全部 LLM 花费。")
    lines.append("")
    lines.append("4. 威胁与边界")
    lines.append("- 意图分布是声明性假设不是线上实测；换分布数字会变（报告与集合构成一起公开即可审计）；")
    lines.append("- 价目为演示值（config.py model_prices，非百炼实价）——降本%是同一价目表内的相对量；")
    lines.append("- 不预设目标值（04 M4：可被集合构成操纵的预设已删除）；")
    lines.append("- A/A' 无意图层，FAQ/闲聊类题也走完整主 Agent（含检索注入）——这正是「不做分档」")
    lines.append("  反事实的真实代价；B 组 HANDOFF 误分诊会零 LLM 短路（如有，errored/分布行可见）；")
    lines.append("- LLM 输出长度天然有方差：同题重跑降本%会小幅波动，量级结论不受影响。")
    lines.append("")
    lines.append("附录 A：聚合 SQL（sids 取附录 B 对应组清单）")
    lines.append(f"  {_AGG_SQL}")
    lines.append(f"  {_TIER_SQL}")
    lines.append("附录 B：各组 sid 清单（精确分账面）")
    for result in results:
        lines.append(f"[{result.key}] {len(result.sids)} 条")
        for i in range(0, len(result.sids), 2):
            lines.append("  " + ", ".join(result.sids[i : i + 2]))
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"报告落盘：{REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

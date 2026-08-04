"""M4.6 实验②：精确缓存降本对照（真实调用；00 §8.1 M4.6 行、plans/m4 第七章）。

模拟流量 = 140 条唯一问题（evals/cost_questions.json cache 节）经 build_cache_traffic
扩成 **200 条请求、恰 30% 历史复述**（分布假设显式声明+精确成立；random.Random(seed=42)
固定种子=流量可逐条重放，tests/obs/test_cost_traffic.py 钉死）。两相位同流量同序对照：
  C = 缓存关（CACHE_TTL_SECONDS=0 → gateway cache=None）——复述照付全价；
  D = 缓存开（TTL=3600 覆盖实验窗；相位前 FLUSH 实验租户缓存键=冷启动）——
      复述期望逐字节命中（缓存 key 只哈希语义本体且 session_id 不入哈希，cache.py:38-42，
      故「每请求一个新会话」不破命中）。
降本% = (cost_C − cost_D) / cost_C，不预设目标值（04 M4）。

口径要点（报告 §1 同文）：
- 驱动=ChatService 生产编排进程内直驱（正常分诊路由；与实验①的 B 组同栈层）——
  缓存的受益面覆盖全管线：fast 分诊、FAQ 直答、主 Agent 各次调用都在缓存面内；
- 命中率自检（计划 §3：对不上=生成器或 key 语义有 bug，先修再报数）：
  按请求级「全命中」核对——某请求的全部 LLM 账行 cached=true 才算命中一个请求；
  期望=恰 60/200 复述请求全命中、140 条首现请求零命中；实测偏差如实进报告，
  复述命中 <54/60 即视为 bug 中止不出报告；
- 相位顺序先关后开（计划 §7 陷阱 2：反序会让开组把缓存烧热污染对照）；
- 实验租户 exp-cache 预算闸关闭；故障注入 0；组间按精确 sid 清单分账（P3）；
- 检索 embedding 无缓存语义、两相位等价支出，不计入对照数字（tier<>'embedding'）；
- 预算硬上限 settings.cost_cache_token_budget（00 §8.0），超限中止落 partial。

用法（仓库根执行；PG/Redis 在跑、迁移与 .env DASHSCOPE key 就位）：
    uv run python scripts/experiment_cost_cache.py --smoke   # 4 唯一×0.5 复述=8 请求连通冒烟
    uv run python scripts/experiment_cost_cache.py           # 完整 200×2 相位 → reports/m4_cost_cache.txt
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from uuid import uuid4

from sqlalchemy import text

# aegis 导入不触发 Settings 实例化（get_settings 惰性 lru_cache）——控制变量 env
# 在每相位装配前落地并 cache_clear 重读（相位切换是本实验的机制核心）。
from aegis.apps.support.rag.retrieve import RetrievalProvider, Retriever
from aegis.apps.support.revalidate import build_precheck
from aegis.apps.support.service import ChatService
from aegis.core.config import get_settings
from aegis.core.db import get_owner_session_factory, get_session_factory
from aegis.core.redis import get_redis
from aegis.core.tenancy import TenantDirectory
from aegis.core.tenant_ctx import tenant_context
from aegis.gateway.factory import build_embedding_client, build_gateway
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.store import SessionRecord

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "m4_cost_cache.txt"

PHASES: tuple[tuple[str, str, str], ...] = (
    ("off", "0", "C=缓存关（CACHE_TTL_SECONDS=0）：复述照付全价"),
    ("on", "3600", "D=缓存开（TTL=3600 覆盖实验窗，相位前 FLUSH 实验租户键=冷启动）"),
)

_AGG_SQL = (
    "SELECT count(*) AS calls, count(*) FILTER (WHERE cached) AS cached_calls, "
    "coalesce(sum(prompt_tokens), 0) AS p, coalesce(sum(completion_tokens), 0) AS c, "
    "coalesce(sum(cost), 0) AS cost "
    "FROM usage_ledger WHERE session_id = ANY(:sids) AND tier <> 'embedding'"
)
_FULLHIT_SQL = (
    "SELECT session_id FROM usage_ledger WHERE session_id = ANY(:sids) AND tier <> 'embedding' "
    "GROUP BY session_id HAVING bool_and(cached)"
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


async def _flush_tenant_cache(tenant_id: str) -> int:
    """相位 D 冷启动：SCAN+DEL 实验租户全部缓存键（key 带租户明文前缀，cache.py:42）。"""
    r = get_redis()
    pattern = f"aegis:cache:v1:{tenant_id}:*"
    deleted = 0
    cursor = 0
    while True:
        cursor, keys = await r.scan(cursor=cursor, match=pattern, count=500)
        if keys:
            deleted += int(await r.delete(*keys))
        if cursor == 0:
            return deleted


@dataclass
class PhaseResult:
    key: str
    caption: str
    sids: list[str] = field(default_factory=list)
    driven: int = 0
    errored: list[int] = field(default_factory=list)


async def main() -> None:
    os.environ["FAULT_INJECTION_RATE"] = "0.0"

    parser = argparse.ArgumentParser(description="M4.6 实验②：精确缓存降本")
    parser.add_argument("--smoke", action="store_true", help="4 唯一×0.5 复述=8 请求冒烟，不写报告")
    args = parser.parse_args()

    common = _load_script("cost_common", "cost_common_for_cache")
    seed = _load_script("seed_demo", "seed_demo_for_cache")
    tid: str = common.CACHE_TENANT_ID
    uid: str = common.CACHE_USER_ID
    pool: list[str] = common.question_strings("cache")
    if args.smoke:
        # 冒烟池刻意异质（faq/rag/tool/闲聊各 1）：0.5 复述率 → 8 请求恰 4 复述
        rows = common.load_questions()["cache"]
        picks = [next(r for r in rows if r["kind"] == k)["question"] for k in ("faq", "rag", "tool", "chitchat")]
        traffic: list[str] = common.build_cache_traffic(picks, replay_ratio=0.5, seed=42)
    else:
        traffic = common.build_cache_traffic(pool, replay_ratio=0.3, seed=42)
    seen: set[str] = set()
    is_replay: list[bool] = []
    for q in traffic:
        is_replay.append(q in seen)
        seen.add(q)
    designed_replays = sum(is_replay)

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.fault_injection_rate == 0.0, "控制变量未生效：故障注入必须关闭"
    budget = settings.cost_cache_token_budget

    owner = get_owner_session_factory()
    sf = get_session_factory()

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
    print(f"[种子] exp-cache 语料：新摄取 {fresh} 续传 {resumed} 跳过 {skipped}（跳过=幂等省钱闸）")

    # ---- 两相位驱动（先关后开；每相位按当刻 settings 重新装配网关与服务）----
    run_tag = uuid4().hex[:8]
    started_at = datetime.now(UTC)
    spent = 0
    partial = False
    results: list[PhaseResult] = []
    for key, ttl, caption in PHASES:
        os.environ["CACHE_TTL_SECONDS"] = ttl
        get_settings.cache_clear()
        phase_settings = get_settings()
        assert phase_settings.cache_ttl_seconds == int(ttl), f"相位 {key} 控制变量未生效"
        if key == "on":
            flushed = await _flush_tenant_cache(tid)
            print(f"[相位 on] FLUSH 实验租户缓存键 {flushed} 条（冷启动）")
        gateway = build_gateway()
        runtime = AgentRuntime(
            gateway,
            sf,
            retrieval=RetrievalProvider(Retriever(sf, build_embedding_client())),
            precheck=build_precheck(sf),
        )
        service = ChatService(
            gateway=gateway, factory=sf, directory=TenantDirectory(sf), runtime=runtime, lock=None, redis=None
        )
        result = PhaseResult(key, caption)
        results.append(result)
        for i, question in enumerate(traffic):
            if spent >= budget:
                partial = True
                break
            sid = f"cost-cache-{key}-{i:03d}-{run_tag}"
            try:
                with tenant_context(tid):
                    await ensure_session(sid)
                    async for _ in service.handle(tenant_id=tid, user_id=uid, session_id=sid, message=question):
                        pass
            except Exception as e:  # 单请求失败不拖垮批次：如实记 errored
                result.errored.append(i)
                print(f"[{key}] #{i:03d} 异常：{type(e).__name__}: {e}")
            result.sids.append(sid)
            result.driven += 1
            delta = await sid_tokens(sid)
            spent += delta
            tag = "复述" if is_replay[i] else "首现"
            print(f"[{key}] #{i:03d} {tag} 完成，token {delta}，累计 {spent}/{budget}")
        if partial:
            print(f"[预算] 累计 {spent} ≥ {budget}，中止批次（{key} 相位止于 {result.driven}/{len(traffic)}）")
            break

    # ---- 对账 sanity + 命中率自检 ----
    async with owner() as s:
        for result in results:
            covered = int((await s.execute(text(_COVERAGE_SQL), {"sids": result.sids})).scalar_one())
            expect = result.driven - len(result.errored)
            if covered < expect:
                raise SystemExit(f"[{result.key}] 账本覆盖 {covered}/{expect}——计量掉账（(58) 面），中止不出报告")
            print(f"[对账] {result.key}: sid 覆盖 {covered}/{expect} OK")
        agg = {r.key: (await s.execute(text(_AGG_SQL), {"sids": r.sids})).one() for r in results}
        fullhit_by_phase = {
            r.key: {row[0] for row in (await s.execute(text(_FULLHIT_SQL), {"sids": r.sids})).all()} for r in results
        }
        embed_row = (await s.execute(text(_EMBED_SQL), {"tid": tid, "floor": embed_floor})).one()

    on_result = next((r for r in results if r.key == "on"), None)
    replay_hits = fresh_hits = 0
    missed_replays: list[int] = []
    if on_result is not None:
        hits = fullhit_by_phase["on"]
        for i, sid in enumerate(on_result.sids):
            if sid in hits:
                if is_replay[i]:
                    replay_hits += 1
                else:
                    fresh_hits += 1
            elif is_replay[i]:
                missed_replays.append(i)
    off_fullhits = len(fullhit_by_phase.get("off", set()))

    for result in results:
        row = agg[result.key]
        print(
            f"[{result.key}] 调用 {row.calls}（cached {row.cached_calls}）"
            f" prompt {row.p} completion {row.c} cost ¥{row.cost}"
        )
    print(
        f"[自检] 设计复述 {designed_replays}/{len(traffic)}；相位 on 请求级全命中："
        f"复述 {replay_hits}/{designed_replays}，首现误命中 {fresh_hits}（应为 0），"
        f"漏命中槽位 {missed_replays}；相位 off 全命中 {off_fullhits}（应为 0）"
    )
    if args.smoke:
        if on_result is not None and (replay_hits < designed_replays or fresh_hits or off_fullhits):
            raise SystemExit("[冒烟] 命中率自检不吻合——先修生成器/key 语义再跑批（计划 §3）")
        print("[冒烟] 通过：两相位连通、复述全命中、关相位零命中。正式跑批不带 --smoke。")
        return
    if on_result is not None and not partial and replay_hits < 54:
        raise SystemExit(f"[自检] 复述命中 {replay_hits}/60 <54——按计划 §3「先修再报数」，中止不出报告")
    if partial:
        print("[partial] 预算中止：相位不可比，本次不计算降本%，报告标记 partial。")

    def pct(base: Decimal, exp: Decimal) -> str:
        return f"{(base - exp) / base * 100:.1f}%" if base else "n/a"

    lines: list[str] = []
    stamp = started_at.strftime("%Y-%m-%d %H:%M:%SZ")
    done_stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    lines.append(f"M4.6 实验②：精确缓存降本（执行 {stamp} → {done_stamp}，run_tag={run_tag}）")
    lines.append("=" * 72)
    lines.append("1. 实验口径")
    lines.append("- 模拟流量：140 条唯一问题（cost_questions.json cache 节，与实验①/评测集零交集）")
    lines.append("  经 build_cache_traffic(replay_ratio=0.3, seed=42) 扩成 200 条请求、恰 60 条复述；")
    lines.append("  分布假设显式声明：30% 历史复述（从已流出前缀均匀重抽，逐字节同串）；")
    lines.append("  唯一池意图构成 FAQ 30%(42)/RAG 40%(56)/工具 20%(28)/闲聊 10%(14)，工具题只读；")
    lines.append("- 驱动：ChatService 生产编排进程内直驱（正常分诊路由），每请求一个新会话——")
    lines.append("  缓存 key 只哈希语义本体（tier/messages/tools/温度/上限），session_id 不入哈希，")
    lines.append("  跨会话复述照样命中（cache.py:38-42）；")
    lines.append("- 相位：先 C（缓存关）后 D（缓存开 TTL=3600，先 FLUSH 实验租户键冷启动）——")
    lines.append("  同流量同序两遍；控制变量装配后断言核验；故障注入 0；预算闸关闭；")
    lines.append(f"- 分账：相位间精确 sid 清单（附录），数字可由 usage_ledger 复算；预算 {budget}；")
    lines.append("- 检索 embedding 无缓存语义、两相位等价支出，不计入对照（tier<>'embedding'）。")
    lines.append("")
    lines.append("2. 原始数字（usage_ledger 聚合，tier<>'embedding'）")
    for result in results:
        row = agg[result.key]
        note = f"；errored {len(result.errored)}：{result.errored}" if result.errored else ""
        lines.append(
            f"- {result.key}: 请求 {result.driven}/{len(traffic)}，LLM 调用 {row.calls}"
            f"（cached {row.cached_calls}），prompt {row.p}，completion {row.c}，cost ¥{row.cost}{note}"
        )
    lines.append(
        f"- embedding 另账（setup 语料种子+两相位检索查询向量）："
        f"{embed_row[0]} 行，{embed_row[1]} token，¥{embed_row[2]}"
    )
    lines.append("")
    lines.append("3. 结果与命中率自检")
    lines.append(
        f"- 命中率自检：设计复述 {designed_replays}/200；相位 on 请求级全命中=复述 {replay_hits}/{designed_replays}、"
    )
    lines.append(
        f"  首现误命中 {fresh_hits}（应 0）、相位 off 全命中 {off_fullhits}（应 0）"
        + (f"；漏命中槽位 {missed_replays}（管线非确定性面，如实登记）" if missed_replays else "；与设计吻合")
    )
    if partial:
        lines.append("- partial：预算中止，相位不可比，本次不计算降本%（诚实缺席）。")
    else:
        cost = {r.key: Decimal(agg[r.key].cost) for r in results}
        lines.append(f"- 精确缓存降本（30% 复述假设下）：{pct(cost['off'], cost['on'])}（C→D，同流量 200 条）")
        lines.append("- 限定语：数字只在「本流量构成 + 30% 复述假设 + 本价目表」口径下成立；")
        lines.append("  复述率是声明性假设——真实流量的降本随实际复述率单调变化，本实验不外推。")
    lines.append("")
    lines.append("4. 威胁与边界")
    lines.append("- 30% 复述是声明的分布假设不是线上实测（生成器与种子公开，构成可审计可重放）；")
    lines.append("- 价目为演示值（config.py model_prices）——降本%是同一价目表内的相对量；")
    lines.append("- 不预设目标值（04 M4）；精确缓存只对逐字节相同请求生效，措辞略异即 miss——")
    lines.append("  本数字是精确缓存的上界口径（语义缓存归 v2，00 §10.3）；")
    lines.append("- LLM 输出长度方差使 C 相位成本有自然波动；D 相位命中部分零方差。")
    lines.append("")
    lines.append("附录 A：聚合/自检 SQL（sids 取附录 B 对应相位清单）")
    lines.append(f"  {_AGG_SQL}")
    lines.append(f"  {_FULLHIT_SQL}")
    lines.append("附录 B：各相位 sid 清单（精确分账面）")
    for result in results:
        lines.append(f"[{result.key}] {len(result.sids)} 条")
        for i in range(0, len(result.sids), 2):
            lines.append("  " + ", ".join(result.sids[i : i + 2]))
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"报告落盘：{REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

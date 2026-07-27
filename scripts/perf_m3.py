"""M3.12② 性能口径实测（真实调用；00 §7.2 第 2 条：缓存命中 <50ms / 未命中首 token <2.5s）。

两口径（本地环境；**实测值超设计值=修正记录而非改口径**——00 §7.2 原文）：
- 口径① 精确缓存命中：3 组唯一问题各二连发（首发真实调用未命中、二发缓存命中），
  计二发**全流消费**耗时（缓存回放是整流不是流式）；fast 档短答省钱——缓存机制
  与档位无关，口径限定语随凭证走；
- 口径② 未命中首 token：20 样本唯一问题（随机后缀保证 miss）、**standard 档**
  （主 Agent 用档=用户体验口径）、计首个 chunk 到达延迟，报 P50/P95 与逐样本值。

预算写死：MAX_CALLS=30 / MAX_COST ¥0.50；max_tokens=64 限输出（省钱且不影响首块口径）。
计量走请求上下文（main 自包 tenant_context——身份宣告封闭名单「脚本 main」位）；
花费以 usage_ledger 账本实测收尾（C25 账单侧）。输出粘贴进 reports/m3_acceptance.md。

    uv run python scripts/perf_m3.py     # 仓库根执行（.env 相对 cwd）
"""

import asyncio
import statistics
import time
import uuid
from decimal import Decimal

from sqlalchemy import text

from aegis.core.db import get_owner_session_factory
from aegis.core.tenant_ctx import tenant_context
from aegis.gateway.factory import build_gateway
from aegis.gateway.schema import LLMRequest, Message
from aegis.runtime.runtime import GatewayLike

TENANT = "tenant-a"
SESSION = f"perf-m3-{uuid.uuid4().hex[:8]}"  # 全脚本统一会话：账本按会话对账；缓存 essence 剔 session 不受影响

MAX_CALLS = 30
MAX_COST_YUAN = Decimal("0.50")

CACHE_ROUNDS = 3
FIRST_TOKEN_SAMPLES = 20
CACHE_TARGET_MS = 50.0
FIRST_TOKEN_TARGET_S = 2.5

_calls = 0


def _req(tier: str, content: str) -> LLMRequest:
    return LLMRequest(
        tier=tier,  # type: ignore[arg-type]  # Tier 是 Literal，脚本参数面收窄即可
        tenant_id=TENANT,
        session_id=SESSION,
        messages=[Message(role="user", content=content)],
        max_tokens=64,
    )


async def _consume(gw: GatewayLike, req: LLMRequest) -> tuple[float, float]:
    """消费整流，返回 (首块延迟 s, 全流耗时 s)；调用计数在此单点递增并核预算。"""
    global _calls
    _calls += 1
    if _calls > MAX_CALLS:
        raise SystemExit(f"调用数超上限 {MAX_CALLS}——中止（预算护栏）")
    t0 = time.perf_counter()
    first: float | None = None
    async for _chunk in gw.complete(req):
        if first is None:
            first = time.perf_counter() - t0
    total = time.perf_counter() - t0
    return (first if first is not None else total), total


async def _spend() -> tuple[int, Decimal, int]:
    """账本对账走 owner 维护面（D4）：app 引擎在 tenant_context 外读 RLS 表=静默空集
    ——首跑实录 tokens=0 的教训（M3.5 偏差(32) 家族：对账面也算维护面）。"""
    stmt = text(
        "SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0),"
        " COALESCE(SUM(cost), 0), COUNT(*) FROM usage_ledger WHERE session_id = :sid"
    )
    async with get_owner_session_factory()() as s:
        row = (await s.execute(stmt, {"sid": SESSION})).one()
    return int(row[0]), Decimal(str(row[1])), int(row[2])


async def main() -> None:
    gw = build_gateway()
    tag = uuid.uuid4().hex[:6]
    with tenant_context(TENANT):
        # 口径①：二连发缓存命中（二发=整流回放耗时）
        print(f"口径① 精确缓存命中（目标 <{CACHE_TARGET_MS:.0f} ms；fast 档短答、二发全流耗时）")
        hit_ms: list[float] = []
        for i in range(CACHE_ROUNDS):
            q = f"演示高频问题 {tag}-{i}：请只回答「好的」两个字。"
            await _consume(gw, _req("fast", q))  # 首发：真实调用入缓存
            _first, total = await _consume(gw, _req("fast", q))  # 二发：命中
            hit_ms.append(total * 1000)
            print(f"  第 {i + 1} 组二发耗时 {total * 1000:7.1f} ms")
        cache_median = statistics.median(hit_ms)
        cache_ok = cache_median < CACHE_TARGET_MS
        print(f"  中位 {cache_median:.1f} ms → {'PASS' if cache_ok else '超设计值（如实记录修正，不改口径）'}\n")

        # 口径②：未命中首 token（standard 档 20 样本）
        print(f"口径② 未命中首 token（目标 <{FIRST_TOKEN_TARGET_S:.1f} s；standard 档、唯一问题保证 miss）")
        firsts: list[float] = []
        for i in range(FIRST_TOKEN_SAMPLES):
            q = f"样本 {tag}-{i}：用一句话说明电商平台退货流程的第 {i + 1} 步该注意什么。"
            first, _total = await _consume(gw, _req("standard", q))
            firsts.append(first)
            print(f"  样本 {i + 1:2d} 首块 {first * 1000:7.0f} ms")
        p50 = statistics.median(firsts)
        p95 = sorted(firsts)[max(0, -(-95 * len(firsts) // 100) - 1)]
        ft_ok = p95 < FIRST_TOKEN_TARGET_S
        ft_verdict = "PASS" if ft_ok else "超设计值（如实记录修正，不改口径）"
        print(f"  P50={p50 * 1000:.0f} ms  P95={p95 * 1000:.0f} ms → {ft_verdict}")

    tokens, cost, calls = await _spend()
    print(
        f"\n账本实测：session={SESSION} tokens={tokens} cost=¥{cost} calls={calls}（上限 {MAX_CALLS}/¥{MAX_COST_YUAN}）"
    )
    if cost > MAX_COST_YUAN:
        raise SystemExit("成本超上限——检查价目与样本量")


if __name__ == "__main__":
    asyncio.run(main())

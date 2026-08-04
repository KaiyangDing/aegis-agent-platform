"""M5.2 口径②：真实上游首 token 分布（小样本；给口径① 的 800ms 假设提供现实参照）。

口径（报告照抄）：**测量点=直连 `build_gateway().complete()` 的首块到达**（D2——
不过 HTTP/SSE：口径② 要的是"上游为真时的首 token"，过全栈会把平台开销混进上游
分布，两组口径就不再正交）；N=100 串行（并发 1）、standard 档、prompt 唯一化、
缓存关、注入关；**不做高并发：费用与厂商限流约束（04 M5 原文理由，原样声明）**。
预算护栏：max_tokens=64 + BUDGET_CEILING_CNY 写死，ledger 圈定本脚本租户核对。

用法（仓库根，.env 带 DASHSCOPE key；PG/Redis 在跑）：
    uv run python scripts/experiment_real_latency.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# 控制变量先于 aegis 消费落 env（先例 experiment_fault_injection.py）
os.environ["CACHE_TTL_SECONDS"] = "0"
os.environ["FAULT_INJECTION_RATE"] = "0.0"
os.environ["LOADTEST_UPSTREAM"] = "0"

from typing import Literal  # noqa: E402

from sqlalchemy import text  # noqa: E402

from aegis.core.config import get_settings  # noqa: E402
from aegis.core.db import get_owner_session_factory  # noqa: E402
from aegis.gateway.factory import build_gateway  # noqa: E402
from aegis.gateway.schema import LLMRequest, Message, TextDelta  # noqa: E402

N = 100
TIER: Literal["standard"] = "standard"
TENANT = "lt-real-latency"
BUDGET_CEILING_CNY = 1.0  # 硬护栏：ledger 实测累计超过即中止
REPORT = REPO_ROOT / "reports" / "m5_real_first_token.txt"


async def _spent_cny() -> float:
    owner = get_owner_session_factory()
    async with owner() as s:
        row = await s.execute(
            text("SELECT coalesce(sum(cost), 0) FROM usage_ledger WHERE tenant_id = :t"), {"t": TENANT}
        )
        return float(row.scalar_one())


def _percentile(sorted_ms: list[float], p: float) -> float:
    idx = min(len(sorted_ms) - 1, max(0, round(p / 100 * (len(sorted_ms) + 1)) - 1))
    return sorted_ms[idx]


async def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.cache_ttl_seconds == 0 and settings.fault_injection_rate == 0.0
    gateway = build_gateway()
    samples_ms: list[float] = []
    errors = 0
    print(f"口径②：N={N} 串行 {TIER} 档，max_tokens=64，预算护栏 ¥{BUDGET_CEILING_CNY}")
    for i in range(N):
        if await _spent_cny() >= BUDGET_CEILING_CNY:
            print(f"[护栏] 账本累计 ≥ ¥{BUDGET_CEILING_CNY}，中止于 {i}/{N}")
            break
        req = LLMRequest(
            tier=TIER,
            messages=[Message(role="user", content=f"延迟探针 {uuid4().hex}，请用一句话回复。")],
            tenant_id=TENANT,
            session_id=f"rl-{uuid4().hex[:10]}",
            max_tokens=64,
        )
        t0 = time.perf_counter()
        first_ms: float | None = None
        try:
            stream = gateway.complete(req)
            async for chunk in stream:
                if isinstance(chunk, TextDelta):
                    first_ms = (time.perf_counter() - t0) * 1000
                    await stream.aclose()  # 首块即测毕：不多花一个不必要的 token 的钱
                    break
        except Exception as e:
            errors += 1
            print(f"  #{i:03d} 异常：{type(e).__name__}")
            continue
        if first_ms is not None:
            samples_ms.append(first_ms)
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{N} 完成，最近首块 {first_ms:.0f}ms")
    if len(samples_ms) < 50:
        raise SystemExit(f"有效样本 {len(samples_ms)} < 50 下限——不出报告（凭证不掺假）")
    spent = await _spent_cny()
    s = sorted(samples_ms)
    p50, p90, p99 = (_percentile(s, p) for p in (50, 90, 99))
    buckets = [(0, 400), (400, 600), (600, 800), (800, 1000), (1000, 1500), (1500, 2500), (2500, 99999)]
    lines = [
        f"== 口径②：真实上游首 token 分布（{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%SZ')}）==",
        "测量点=直连 build_gateway().complete() 首个 TextDelta（D2：不过 HTTP/SSE——两组口径正交）",
        f"N={len(s)}（目标 {N}，异常 {errors}）；{TIER} 档串行；prompt 唯一化；缓存关；注入关；max_tokens=64",
        "不做高并发：费用与厂商限流约束（04 M5 原文理由）",
        "",
        f"P50 = {p50:.0f} ms    P90 = {p90:.0f} ms    P99 = {p99:.0f} ms",
        f"min = {s[0]:.0f} ms   max = {s[-1]:.0f} ms",
        "",
        "直方图（ms 桶 | 样本数）：",
    ]
    for lo, hi in buckets:
        n = sum(1 for v in s if lo <= v < hi)
        label = f"{lo}-{hi}" if hi < 99999 else f">{lo}"
        lines.append(f"  {label:>10} | {'#' * n}{' ' if n else ''}({n})")
    lines += [
        "",
        f"真实花费：ledger 记 ¥{spent:.4f}——首块即 aclose 使流未到 UsageChunk，计量单点"
        f"无账可记（**盲区非零调用**；供应商侧照常计费）。上界估算 ≈{len(s) * 94 / 1000:.1f}k token"
        f"≈ ≤¥{len(s) * 94 * 0.0035 / 1000:.2f}（护栏 ¥{BUDGET_CEILING_CNY} 写死）",
        f"与口径① 对照：模拟参数 800ms 相对实测 P50 {p50:.0f}ms "
        + ("属真实量级偏保守。" if p50 <= 800 else "偏乐观——口径① 报告读数时须带本句。"),
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"报告落盘：{REPORT}")


if __name__ == "__main__":
    asyncio.run(main())

"""M1 毕业实验：故障注入下的网关韧性实测 + 熔断演示。

口径（写死，报告照抄）：
- 主实验：N=1000、fast 档、仅对 bailian:qwen-flash 注入 30% 失败、重试最多 3 次尝试、
  同档 fallback、缓存关闭、并发 10、限流临时放宽 20 QPS（提速用，不影响成功率口径）；
- 熔断演示：单候选路由 + 100% 注入——零真实调用、零费用，观察打开前后延迟塌缩。

    uv run python scripts/experiment_fault_injection.py

预计 2–4 分钟，真实花费 < ¥0.1（qwen-flash 短问答）。需要 Redis 与 PG 在跑。
"""

import asyncio
import os
import time
import uuid
from collections import Counter
from pathlib import Path

# 必须在 import aegis 之前设好实验环境（环境变量 > .env）
os.environ["FAULT_INJECTION_RATE"] = "0.3"
os.environ["FAULT_INJECTION_TARGETS"] = '["bailian:qwen-flash"]'
os.environ["CACHE_TTL_SECONDS"] = "0"
os.environ["PROVIDER_RATE"] = "20"
os.environ["PROVIDER_BURST"] = "40"
os.environ["TENANT_RATE"] = "20"
os.environ["TENANT_BURST"] = "40"

from sqlalchemy import text  # noqa: E402

from aegis.core.config import get_settings  # noqa: E402
from aegis.core.db import get_session_factory  # noqa: E402
from aegis.core.redis import get_redis  # noqa: E402
from aegis.gateway.factory import build_gateway  # noqa: E402
from aegis.gateway.providers.openai_compat import OpenAICompatProvider  # noqa: E402
from aegis.gateway.schema import LLMRequest, Message, UsageChunk  # noqa: E402

# 报告锚定项目根，不受"从哪个目录运行"影响（PyCharm 默认 cwd=脚本目录，
# 会把相对路径 reports/ 写成 scripts/reports/）
ROOT = Path(__file__).resolve().parent.parent  # scripts/ 的上一级 = 项目根

N = 1000
WORKERS = 10
TENANT = f"exp-{uuid.uuid4().hex[:6]}"

_CB_KEYS = ("aegis:cb:bailian:open", "aegis:cb:bailian:fails", "aegis:cb:bailian:probe")


def make_req(i: int, tenant: str) -> LLMRequest:
    return LLMRequest(
        tier="fast",
        tenant_id=tenant,
        messages=[Message(role="user", content=f"实验第 {i} 号：请只回复数字 {i}")],
        max_tokens=16,
    )


async def one_call(gw, i: int) -> dict:
    t0 = time.perf_counter()
    model = ""
    try:
        async for chunk in gw.complete(make_req(i, TENANT)):
            if isinstance(chunk, UsageChunk):
                model = chunk.model
        return {"ok": True, "sec": time.perf_counter() - t0, "model": model}
    except Exception as e:
        return {"ok": False, "sec": time.perf_counter() - t0, "err": type(e).__name__}


async def phase_a(gw) -> tuple[list[str], int]:
    sem = asyncio.Semaphore(WORKERS)
    done = 0

    async def guarded(i: int) -> dict:
        nonlocal done
        async with sem:
            r = await one_call(gw, i)
            done += 1
            if done % 100 == 0:
                print(f"  进度 {done}/{N}")
            return r

    t0 = time.perf_counter()
    results = await asyncio.gather(*(guarded(i) for i in range(N)))
    wall = time.perf_counter() - t0

    oks = [r for r in results if r["ok"]]
    lat = sorted(r["sec"] for r in oks)

    def pct(p: float) -> float:
        return lat[min(len(lat) - 1, int(len(lat) * p))]

    models = Counter(r["model"] for r in oks)
    errors = Counter(r["err"] for r in results if not r["ok"])
    lines = [
        "== 主实验：30% 注入 / 1000 次 / fast 档 ==",
        f"  成功 {len(oks)}/{N} = {len(oks) / N:.2%}（目标 ≥99%）",
        f"  延迟  P50 {pct(0.50):.2f}s   P95 {pct(0.95):.2f}s   P99 {pct(0.99):.2f}s",
        f"  模型分布 {dict(models)}（理论：三连败 0.3³=2.7% 落到 fallback）",
        f"  失败类型 {dict(errors) or '无'}",
        f"  实验墙钟 {wall:.0f}s，并发 {WORKERS}，限流口径 20 QPS",
    ]
    return lines, len(oks)


async def phase_b() -> list[str]:
    s = get_settings()
    redis = get_redis()
    await redis.delete(*_CB_KEYS)  # 清场：主实验可能留下零星失败计数

    from aegis.gateway.breaker import CircuitBreaker
    from aegis.gateway.ratelimit import RateLimiter
    from aegis.gateway.router import Candidate, LLMGateway

    gw = LLMGateway(
        providers={
            "bailian": OpenAICompatProvider(
                "bailian", s.dashscope_base_url, s.dashscope_api_key.get_secret_value()
            )
        },
        routes={"fast": [Candidate("bailian", "qwen-flash")]},  # 单候选：无路可退的绝境
        breaker=CircuitBreaker(redis),  # 默认阈值 5 / open 30s
        limiter=RateLimiter(redis),
        fault_rate=1.0,  # 100% 注入：零真实调用、零费用
        fault_targets=frozenset({"bailian:qwen-flash"}),
    )
    lines = ["", "== 熔断演示：100% 注入 / 单候选 =="]
    for i in range(1, 16):
        t0 = time.perf_counter()
        try:
            async for _ in gw.complete(make_req(i, f"{TENANT}-cb")):
                pass
            outcome = "成功?!"
        except Exception as e:
            outcome = type(e).__name__
        ms = (time.perf_counter() - t0) * 1000
        state = "OPEN" if await redis.exists("aegis:cb:bailian:open") else "closed"
        lines.append(f"  #{i:02d}  {outcome:<24s} {ms:8.1f}ms  熔断:{state}")
    ttl = await redis.ttl("aegis:cb:bailian:open")
    lines += [
        f"  → 打开后（TTL {ttl}s）请求毫秒级失败 = 零穿透",
        "    （重试退避最少百毫秒级，毫秒级失败证明连重试层都没进；且注入先于任何",
        "     真实调用发生——本幕上游流量为 0）",
    ]
    await redis.delete(*_CB_KEYS)
    lines.append("  → 演示现场已清理（熔断键删除）")
    return lines


async def ledger_check(success_count: int) -> list[str]:
    async with get_session_factory()() as session:
        row = (
            await session.execute(
                text(
                    "SELECT count(*), COALESCE(sum(prompt_tokens+completion_tokens),0),"
                    " COALESCE(sum(cost),0) FROM usage_ledger WHERE tenant_id = :t"
                ),
                {"t": TENANT},
            )
        ).one()
    match = "一致 ✓" if row[0] == success_count else f"缺口 {success_count - row[0]} 行！"
    return [
        "",
        "== 账本核对 ==",
        f"  成功 {success_count} 次 vs 账本 {row[0]} 行 → {match}",
        f"  token 合计 {row[1]}，实验花费 ¥{row[2]}",
    ]


async def main() -> None:
    print(f"实验租户：{TENANT}（唯一，账本可精确圈定本次实验）")
    gw = build_gateway()
    lines = [
        "M1 故障注入实验报告",
        f"口径：N={N}，仅 bailian:qwen-flash 注入 30%，重试≤3 次，同档 fallback，"
        f"缓存关闭，并发 {WORKERS}，限流 20 QPS（实验放宽）",
        "",
    ]
    a_lines, success = await phase_a(gw)
    lines += a_lines
    lines += await phase_b()
    lines += await ledger_check(success)
    report = "\n".join(lines)
    print("\n" + report)
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    out = reports_dir / "m1_fault_injection.txt"
    out.write_text(report, encoding="utf-8")
    print(f"\n报告已写入 {out}（提交它——简历数字的原始凭证）")


if __name__ == "__main__":
    asyncio.run(main())

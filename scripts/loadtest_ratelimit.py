"""限流精度压测：多协程并发抢令牌，验证放行总量与理论值的误差 < 5%。

    uv run python scripts/loadtest_ratelimit.py

理论放行数 = capacity（开局满桶） + rate × duration。
时序敏感的精度断言不进 CI（必然偶发红），以本脚本的报告为准——M1 验收项之一。
"""

import asyncio
import time
import uuid

import redis.asyncio as aioredis

from aegis.gateway.ratelimit import RateLimiter

REDIS_URL = "redis://localhost:6379/9"
RATE = 50.0  # 每秒补 50 个令牌
CAPACITY = 25.0
DURATION = 10.0  # 压 10 秒
WORKERS = 20  # 20 个协程并发抢


async def worker(rl: RateLimiter, scope: str, end: float) -> tuple[int, int]:
    allowed = attempts = 0
    while time.monotonic() < end:
        ok, _ = await rl.try_take(scope, RATE, CAPACITY)
        attempts += 1
        if ok:
            allowed += 1
        await asyncio.sleep(0.002)  # 每协程约 500 次/秒的进攻压力
    return allowed, attempts


async def main() -> None:
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    rl = RateLimiter(client)
    scope = f"loadtest:{uuid.uuid4().hex[:8]}"

    end = time.monotonic() + DURATION
    results = await asyncio.gather(*(worker(rl, scope, end) for _ in range(WORKERS)))
    allowed = sum(a for a, _ in results)
    attempts = sum(t for _, t in results)

    expected = CAPACITY + RATE * DURATION
    error = abs(allowed - expected) / expected
    print(f"进攻压力：{WORKERS} 协程 / {attempts} 次尝试 / {DURATION}s")
    print(f"放行：{allowed}   理论值：{expected:.0f}   误差：{error:.2%}")
    print("✅ PASS（< 5%）" if error < 0.05 else "❌ FAIL（≥ 5%）——贴给 Claude 排查")
    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())

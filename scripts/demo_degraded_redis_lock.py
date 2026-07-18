"""M2.12 停 Redis 降级演示：会话锁降级 PG advisory，互斥保住而非放弃（00 §6.2 第 6 项前半）。

操作顺序：
  1) docker stop aegis-redis
  2) uv run python scripts/demo_degraded_redis_lock.py     # 仓库根；需 PG 在跑
  3) docker start aegis-redis
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from aegis.core.locks import build_session_lock, new_owner_token
from aegis.core.redis import get_redis

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "m2_degradation_redis.txt"
SESSION_ID = f"demo-lock-{uuid.uuid4().hex[:8]}"
LOG: list[str] = []


def log(line: str) -> None:
    print(line)
    LOG.append(line)


async def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="  [降级日志] %(message)s")
    try:
        await get_redis().ping()
    except Exception as e:
        log(f"前置确认：Redis 不可达（{type(e).__name__}）——演示条件成立")
    else:
        raise SystemExit("Redis 仍在运行——请先 docker stop aegis-redis 再跑本演示")

    # 生产组装（Redis 主 + PG advisory 降级）：演示的就是生产降级行为；单 asyncio.run 单 loop 安全
    lock = build_session_lock()
    token_a, token_b = new_owner_token(), new_owner_token()
    log(f"并发两协程抢同一会话锁 session={SESSION_ID}")
    got_a, got_b = await asyncio.gather(lock.acquire(SESSION_ID, token_a), lock.acquire(SESSION_ID, token_b))
    log(f"  协程 A acquire -> {got_a}；协程 B acquire -> {got_b}")
    if got_a == got_b:
        raise SystemExit(f"互斥破产：两者同为 {got_a}——演示失败")
    winner, loser = (token_a, token_b) if got_a else (token_b, token_a)
    log("  恰一个获锁成功（PG advisory 在降级期承接互斥）")
    log(f"  赢家释放 -> {await lock.release(SESSION_ID, winner)}")
    log(f"  输家重试 acquire -> {await lock.acquire(SESSION_ID, loser)}（释放后可得）")
    log(f"  输家释放 -> {await lock.release(SESSION_ID, loser)}")
    log("结论：Redis 不可用期间互斥语义由 PG advisory lock 保住——降级换后端，不放弃锁（M2.9 C4）")
    log("收尾提醒：docker start aegis-redis")
    REPORT_PATH.write_text("\n".join(LOG) + "\n", encoding="utf-8")
    print(f"实录已落盘：{REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

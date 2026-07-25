"""意图分类延迟实测（M3.6②；记录供 M3.12 性能口径参考，M5.2 口径②同族）。

用法（仓库根执行——.env 相对 cwd 加载）：

    uv run python scripts/measure_intent_latency.py

真实调用口径（00 §7.0）：M3 开发调试允许。恰 5 次 fast 档分类调用——四类探针
各一（意图中不中只作 prompt 质量信号，验收判据是延迟：fast 档 <1s）+ 重复首条
（同租户同 messages → 网关精确缓存命中，<50ms 口径的先导观察，正式验收 M3.12）。
预算：探针清单写死 = 调用次数上限写死；单次输出 1-2 token，总成本 < ¥0.001，
月度预算闸门与控制台限额告警双兜底。
计量走 app 角色引擎（RLS）：main 自包 tenant_context（身份宣告封闭名单第四处）；
会在 usage_ledger 留 5 行真实计量行（test_usage 已随机租户化，残留免疫）。
首测记录（2026-07-25）：新鲜 2357/976/901/947 ms（首条含连接建立，后三条 <1s
达标）、缓存命中 8 ms、分类 4/4 全中。
"""

import asyncio
import logging
import time

from aegis.apps.support.intent import Intent, classify
from aegis.core.tenant_ctx import tenant_context
from aegis.gateway.factory import build_gateway
from aegis.runtime.runtime import GatewayLike

# 四类各一条探针；预期意图只作 prompt 质量信号记录，验收判据是延迟（fast 档 <1s）
PROBES: list[tuple[str, Intent]] = [
    ("你好，请问你们平台客服几点上班？", Intent.FAQ),
    ("你们的退货政策是什么？是七天无理由吗？", Intent.RAG),
    ("帮我查一下订单 AZ-1001 的物流到哪了", Intent.TOOL),
    ("我要投诉你们，立刻给我转人工！", Intent.HANDOFF),
]
TENANT = "tenant-a"
SESSION = "m36-latency-probe"


async def _timed(gw: GatewayLike, text: str) -> tuple[Intent, float]:
    t0 = time.perf_counter()
    got = await classify(gw, text, tenant_id=TENANT, session_id=SESSION)
    return got, time.perf_counter() - t0


async def main() -> None:
    logging.basicConfig(level=logging.WARNING)  # classify 是 fail-open：warning 必须可见
    gw = build_gateway()
    all_hit = True
    with tenant_context(TENANT):
        for text, expected in PROBES:
            got, dt = await _timed(gw, text)
            hit = got is expected
            all_hit = all_hit and hit
            mark = "中" if hit else "偏"
            print(f"[{mark}] {dt * 1000:6.0f} ms  实测={got.value:<8} 预期={expected.value:<8} {text}")
        got, dt = await _timed(gw, PROBES[0][0])
        print(f"\n重复首条（精确缓存命中路径）：{dt * 1000:.0f} ms → {got.value}")
    verdict = "4/4 全中" if all_hit else "有偏分项（见上表）——prompt 质量信号，如实记录"
    print(f"分类正确率：{verdict}")


if __name__ == "__main__":
    asyncio.run(main())

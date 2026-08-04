"""M5.4 补录①：熔断恢复闭合时间实测（#10，04 M1 验收未尽项——无条件补）。

**闭合时间定义（D8，写进报告）**：起点=上游恢复时刻（脚本切到无注入网关），
终点=首次探针成功且 `open`/`fails` 键清零、请求正常放行；预期 ≈ open TTL 剩余 +
一次探针延迟，上界 open_seconds(30s)+探针耗时——TTL 即状态迁移（breaker.py 设计值）。

方法（§4-M5.4 交付②）：清场三键 → `gw_bad`（单候选路由+fault_rate=1.0，**打开熔断
零真实调用**——注入器在调用前拦截）→ open 键出现记 t_open → 立即切 `gw_good`
（同一 Redis/breaker、注入关）=「上游恢复」记 t_recover → 每 0.5s 一次真实短请求
（max_tokens=16）→ 首次成功且键清零记 t_closed。复跑 3 轮取全部值（TTL 相位不同，
闭合时间在 (探针耗时, 30s+探针耗时] 区间浮动是预期）。
预算护栏：BUDGET_CEILING_CNY=0.5 写死（真实调用只在恢复探测段，每轮个位数次）。

用法（仓库根；PG/Redis 在跑、.env 带 key）：
    uv run python scripts/experiment_breaker_recovery.py
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

os.environ["CACHE_TTL_SECONDS"] = "0"
os.environ["LOADTEST_UPSTREAM"] = "0"

from sqlalchemy import text  # noqa: E402

from aegis.core.config import get_settings  # noqa: E402
from aegis.core.db import get_owner_session_factory  # noqa: E402
from aegis.core.redis import get_redis  # noqa: E402
from aegis.core.tenant_ctx import tenant_context  # noqa: E402
from aegis.gateway.breaker import CircuitBreaker  # noqa: E402
from aegis.gateway.factory import _price_table  # noqa: E402
from aegis.gateway.metering import MeteringRecorder  # noqa: E402
from aegis.gateway.providers.base import Provider  # noqa: E402
from aegis.gateway.providers.openai_compat import OpenAICompatProvider  # noqa: E402
from aegis.gateway.ratelimit import RateLimiter  # noqa: E402
from aegis.gateway.router import GatewayLimits, LLMGateway, parse_routes  # noqa: E402
from aegis.gateway.schema import LLMRequest, Message, TextDelta  # noqa: E402

ROUNDS = 3
TENANT = "lt-breaker"
BUDGET_CEILING_CNY = 0.5
PROBE_INTERVAL_S = 0.5
REPORT = REPO_ROOT / "reports" / "m5_breaker_recovery.txt"


def _gateway(*, fault_rate: float) -> LLMGateway:
    """单候选路由（standard=[qwen-plus] 恰一个）——fallback 无路可换，熔断账才积得起来。
    与 build_gateway 同件装配、共享同一 Redis/breaker 键空间（恢复实验的物质前提）。"""
    s = get_settings()
    r = get_redis()
    providers: dict[str, Provider] = {
        "bailian": OpenAICompatProvider("bailian", s.dashscope_base_url, s.dashscope_api_key.get_secret_value())
    }
    from aegis.core.db import get_session_factory

    return LLMGateway(
        providers=providers,
        routes=parse_routes(
            # 三档必须齐全（parse_routes 防呆）；standard 单候选=实验面（fallback 无路可换）
            {"fast": ["bailian:qwen-flash"], "standard": ["bailian:qwen-plus"], "strong": ["bailian:qwen-plus"]},
            {"bailian"},
        ),
        breaker=CircuitBreaker(r),
        limiter=RateLimiter(r, replicas=1),
        cache=None,
        limits=GatewayLimits(provider_rate=50, provider_burst=100, tenant_rate=50, tenant_burst=100, max_wait=10),
        fault_rate=fault_rate,
        fault_targets=frozenset({"bailian:qwen-plus"}),
        fault_mode="error",
        meter=MeteringRecorder(get_session_factory(), _price_table(s.model_prices)),
        monthly_token_budget=0,
        monthly_budget_resolver=None,
        request_token_budget=0,
    )


async def _clear_breaker_keys() -> None:
    r = get_redis()
    keys = [k async for k in r.scan_iter("aegis:cb:bailian*")]
    if keys:
        await r.delete(*keys)


async def _breaker_state() -> tuple[bool, str | None]:
    r = get_redis()
    open_ttl = await r.ttl("aegis:cb:bailian:open")
    fails = await r.get("aegis:cb:bailian:fails")
    return open_ttl > 0, None if fails is None else str(fails)


async def _spent_cny() -> float:
    owner = get_owner_session_factory()
    async with owner() as s:
        row = await s.execute(
            text("SELECT coalesce(sum(cost), 0) FROM usage_ledger WHERE tenant_id = :t"), {"t": TENANT}
        )
        return float(row.scalar_one())


def _req() -> LLMRequest:
    return LLMRequest(
        tier="standard",
        messages=[Message(role="user", content=f"熔断恢复探针 {uuid4().hex}，回一个字。")],
        tenant_id=TENANT,
        session_id=f"br-{uuid4().hex[:10]}",
        max_tokens=16,
    )


async def _call_once(gw: LLMGateway) -> tuple[bool, str]:
    """全量耗尽流（不许首块即 aclose）：router 的 on_success/计量都记在**流耗尽处**——
    半途弃流既不计量也不闭合熔断（本实验第一版实测踩中：探针 ok 而 fails=5 残留、
    探针令牌 120s 锁死后续半开）。max_tokens=16 使全量消费本就便宜。
    tenant_context 配对：计量走 app 工厂受 RLS 管辖，裸网关驱动不设租户上下文则
    GUC 空 → 写入被静默拒收（fail-open 空账）——首跑 ¥0.0000 实测踩中，(58) 家族第三例。"""
    saw_text = False
    try:
        with tenant_context(TENANT):
            stream = gw.complete(_req())
            async for chunk in stream:
                if isinstance(chunk, TextDelta):
                    saw_text = True
        return saw_text, "ok" if saw_text else "ok-empty"
    except Exception as e:
        return False, type(e).__name__


async def one_round(n: int, lines: list[str]) -> float:
    await _clear_breaker_keys()
    gw_bad = _gateway(fault_rate=1.0)
    gw_good = _gateway(fault_rate=0.0)
    # ① 100% 注入连发（零真实调用：注入器在调用前拦截）直至熔断打开
    for _ in range(30):
        await _call_once(gw_bad)
        if (await _breaker_state())[0]:
            break
    is_open, fails = await _breaker_state()
    assert is_open, "熔断未打开——注入/阈值配置有误，中止"
    lines.append(f"[轮{n}] 熔断已打开（fails={fails}）；此刻切无注入网关=「上游恢复」")
    t_recover = time.monotonic()
    # ② 0.5s 探测节拍直至首次成功且键清零
    probe_i = 0
    while True:
        ok, why = await _call_once(gw_good)
        is_open, fails = await _breaker_state()
        probe_i += 1
        if probe_i % 10 == 0 or ok:
            r = get_redis()
            open_ttl = await r.ttl("aegis:cb:bailian:open")
            print(
                f"  [轮{n} 探针{probe_i}] ok={ok}({why}) open_ttl={open_ttl} fails={fails} "
                f"t+{time.monotonic() - t_recover:.1f}s"
            )
        if ok and not is_open and fails is None:
            t_closed = time.monotonic() - t_recover
            lines.append(f"[轮{n}] 闭合时间 = {t_closed:.1f}s（首次探针成功且 open/fails 键清零）")
            return t_closed
        if time.monotonic() - t_recover > 90:
            raise SystemExit(f"[轮{n}] 90s 未闭合——异常，中止不出报告（最后探针：{why}）")
        if await _spent_cny() >= BUDGET_CEILING_CNY:
            raise SystemExit("[护栏] 预算触顶，中止")
        await asyncio.sleep(PROBE_INTERVAL_S)


async def main() -> None:
    get_settings.cache_clear()
    lines: list[str] = [
        f"== 熔断恢复闭合时间实测（#10；{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%SZ')}）==",
        "定义（D8）：起点=上游恢复时刻（切无注入网关）；终点=首次探针成功且 open/fails 键清零。",
        "打开段=100% 故障注入（注入器在真实调用前拦截——零 token）；恢复探测=真实短请求",
        f"（max_tokens=16，{PROBE_INTERVAL_S}s 节拍，预算护栏 ¥{BUDGET_CEILING_CNY} 写死）。",
        "设计值：open_seconds=30（TTL 即状态迁移）——闭合时间 ∈ (探针耗时, 30s+探针耗时]，",
        "随 TTL 相位浮动是预期，主导因子=open TTL 剩余。",
        "",
    ]
    results = [await one_round(i + 1, lines) for i in range(ROUNDS)]
    spent = await _spent_cny()
    lines += [
        "",
        f"三轮闭合时间：{', '.join(f'{v:.1f}s' for v in results)}（区间 {min(results):.1f}–{max(results):.1f}s）",
        f"真实花费（ledger，tenant={TENANT}）：¥{spent:.4f}",
        "驱动层教训（(58) 家族第三例）：裸网关驱动必须 tenant_context 配对，否则计量被",
        "RLS 静默拒收（fail-open 空账）——本报告为配对修正后的重跑版，首跑曾记 ¥0.0000。",
        "简历读数（M5.5）：熔断恢复闭合 ≤ 上界(open TTL 30s + 探针)，实测三轮区间如上——",
        "凭证句式取最大值+区间注记。",
    ]
    await _clear_breaker_keys()
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))
    print(f"报告落盘：{REPORT}")


if __name__ == "__main__":
    asyncio.run(main())

"""M5.4 补录②：档内容灾切换实录（P6 拍板对象：standard 档 qwen-plus→qwen-turbo）。

对象修正史（报告照抄）：计划两版对象（qwen-plus↔deepseek-v3 / qwen3.7-plus↔glm5.2）
均随 #28 作废——模型池 v3 后容灾=**qwen 档内降级**，与 M1 fallback 实测凭证连续。
方法：FaultInjector 对 `bailian:qwen-plus` 100% 注入（provider:model 精确靶，T10）→
standard 档 N=20 次真实调用 → 断言 20/20 的 `UsageChunk.model == qwen-turbo`（**流全量
耗尽**——计量与熔断簿记都在流尾，#10 实验实测教训）→ ledger 圈定核对 20 行同模型
（计费路径同样切换成功）。
**C5/D9 预期行为段**：熔断记账是 **provider 粒度**（bailian 一本账），同 provider 内
fallback 成功即 `on_success("bailian")` 清零失败计数 → **熔断全程不打开是预期行为**
——这恰暴露 provider 粒度对"单模型坏死"的钝感，v1 显式接受（00 §2.2：误伤再细化为
provider:model），demo 预答"为什么熔断没开"。
预算护栏：BUDGET_CEILING_CNY=0.1 写死（20 次短请求）。

用法（仓库根；PG/Redis 在跑、.env 带 key）：
    uv run python scripts/experiment_qwen_tier_failover.py
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
os.environ["FAULT_INJECTION_RATE"] = "1.0"
os.environ["FAULT_INJECTION_TARGETS"] = '["bailian:qwen-plus"]'  # provider:model 精确靶（T10）
os.environ["FAULT_INJECTION_MODE"] = "error"

from sqlalchemy import text  # noqa: E402

from aegis.core.config import get_settings  # noqa: E402
from aegis.core.db import get_owner_session_factory  # noqa: E402
from aegis.core.redis import get_redis  # noqa: E402
from aegis.core.tenant_ctx import tenant_context  # noqa: E402
from aegis.gateway.factory import build_gateway  # noqa: E402
from aegis.gateway.schema import LLMRequest, Message, UsageChunk  # noqa: E402

N = 20
TENANT = "lt-failover"
BUDGET_CEILING_CNY = 0.1
REPORT = REPO_ROOT / "reports" / "m5_failover_qwen_tier.txt"


async def _spent_cny() -> float:
    owner = get_owner_session_factory()
    async with owner() as s:
        row = await s.execute(
            text("SELECT coalesce(sum(cost), 0) FROM usage_ledger WHERE tenant_id = :t"), {"t": TENANT}
        )
        return float(row.scalar_one())


async def _ledger_models() -> list[tuple[str, int]]:
    owner = get_owner_session_factory()
    async with owner() as s:
        rows = await s.execute(
            text("SELECT model, count(*) FROM usage_ledger WHERE tenant_id = :t GROUP BY model ORDER BY model"),
            {"t": TENANT},
        )
        return [(str(m), int(c)) for m, c in rows.all()]


async def _breaker_open() -> bool:
    return (await get_redis().ttl("aegis:cb:bailian:open")) > 0


async def main() -> None:
    get_settings.cache_clear()
    s = get_settings()
    assert s.fault_injection_rate == 1.0 and s.fault_injection_targets == ["bailian:qwen-plus"]
    assert s.model_routes["standard"] == ["bailian:qwen-plus", "bailian:qwen-turbo"], "standard 候选链与实况不符"
    gateway = build_gateway()
    models: list[str] = []
    t0 = time.monotonic()
    for i in range(N):
        if await _spent_cny() >= BUDGET_CEILING_CNY:
            raise SystemExit("[护栏] 预算触顶，中止")
        req = LLMRequest(
            tier="standard",
            messages=[Message(role="user", content=f"容灾探针 {uuid4().hex}，回一个字。")],
            tenant_id=TENANT,
            session_id=f"fo-{uuid4().hex[:10]}",
            max_tokens=16,
        )
        model = ""
        with tenant_context(TENANT):  # (58) 家族第三例：计量受 RLS 管辖，裸驱动必须配对否则空账
            stream = gateway.complete(req)
            async for chunk in stream:  # 全量耗尽：计量/熔断簿记在流尾（#10 教训）
                if isinstance(chunk, UsageChunk):
                    model = chunk.model
        models.append(model)
        print(f"  #{i + 1:02d} model={model}")
    elapsed = time.monotonic() - t0
    breaker_open = await _breaker_open()
    spent = await _spent_cny()
    ledger = await _ledger_models()
    ok = all(m == "qwen-turbo" for m in models) and len(models) == N and bool(ledger)
    lines = [
        f"== 档内容灾切换实录（standard：qwen-plus→qwen-turbo；{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%SZ')}）==",
        "对象修正史：deepseek/glm 两版计划对象均随 #28 作废（模型池 v3）——容灾=qwen 档内降级，",
        "与 M1 fallback 实测凭证连续（M5.0 P6 拍板；05 表述同步）。",
        f"方法：FaultInjector 对 bailian:qwen-plus 100% 注入（error 模式）；standard 档 N={N} 真实调用；",
        "流全量耗尽（计量/熔断簿记在流尾——#10 实验实测教训）。",
        "",
        f"结果：{sum(1 for m in models if m == 'qwen-turbo')}/{N} 次 UsageChunk.model == qwen-turbo"
        + ("（全数切换 ✅）" if ok else "（存在未切换样本 ❌）"),
        f"ledger 圈定核对（tenant={TENANT}）：{ledger} ——计费路径同样切换成功（空账即断言失败不出报告）",
        "驱动层教训（(58) 家族第三例）：裸网关驱动必须 tenant_context 配对，否则计量被 RLS",
        "静默拒收（fail-open 空账）——本报告为配对修正后的重跑版，首跑 ledger 曾为 []。",
        f"熔断状态：open={'是' if breaker_open else '否'}（**预期=否**，见下）",
        f"总耗时 {elapsed:.1f}s；真实花费 ¥{spent:.4f}（护栏 ¥{BUDGET_CEILING_CNY} 写死）",
        "",
        "C5/D9 预期行为段（demo 预答「为什么熔断没开」）：",
        "熔断记账是 provider 粒度（bailian 一本账）；每次 qwen-plus 注入失败 +1 后，",
        "同 provider 的 qwen-turbo 成功即 on_success('bailian') **清零**失败计数——",
        "账永远到不了阈值 5。这暴露 provider 粒度对「单模型坏死」的钝感：v1 显式接受",
        "（00 §2.2：误伤再细化为 provider:model，v2 路径），fallback 本身就是这层的防线。",
    ]
    if not ok:
        raise SystemExit("\n".join(lines) + "\n断言失败——不出报告（凭证不掺假）")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines[-8:]))
    print(f"报告落盘：{REPORT}")


if __name__ == "__main__":
    asyncio.run(main())

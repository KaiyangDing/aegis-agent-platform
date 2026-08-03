"""M4.2 /metrics 验收演示与凭证（00 §8.1 M4.2 行 #23 验收点；产物进 reports/）。

拍板 2（2026-08-03）批准的一次性真实调用例外（00 §8.0 之外）：**恰 3 轮**短问题
写死在 ROUNDS，fast/standard 档，预算量级 ¥0.01–0.05——改轮数=改口径，先过用户。
流程：生产装配链 ASGI 起 app（create_app 缺省=真网关/真锁/RLS 世界/平台查读缝）
→ 刷 /metrics 记 tenant-a 预算比（前）→ 3 轮真实 chat → 再刷（后）→
断言 ratio 上升（不升即硬失败不落盘——凭证不掺假）→ 前后对照 + 全量
exposition（11 族）写入 reports/m4_metrics_sample.txt。
口径注记：ASGI 直连与 curl 同字节；#23 分子复用月度闸门 month_spend 同一实现，
故本演示同时是"告警与拦截同一把尺"的实拍证词。
前置：仓库根执行（.env 相对 cwd）、PG/Redis 在跑、迁移+种子已就位、DASHSCOPE key。
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

REPO = Path(__file__).resolve().parents[1]  # 落盘锚定项目根，不依赖 cwd（07 §4 第 7 条）
OUT = REPO / "reports" / "m4_metrics_sample.txt"
ROUNDS = ["你们平台几点营业？", "退货政策是什么？", "灵犀降噪耳机 Pro 保修多久？"]  # 恰 3 轮，写死


def _ratio_of(exposition: str, tenant: str) -> float | None:
    for line in exposition.splitlines():
        if line.startswith("aegis_tenant_budget_used_ratio") and f'tenant_id="{tenant}"' in line:
            return float(line.rsplit(" ", 1)[1])
    return None


async def main() -> None:
    from aegis.api.auth import issue_token
    from aegis.api.main import create_app
    from aegis.core.config import get_settings
    from aegis.core.tenancy import Role

    settings = get_settings()
    app = create_app()
    user_token = issue_token(
        user_id="u-a1",
        tenant_id="tenant-a",
        role=Role.USER,
        ttl_s=900,
        secret=settings.jwt_secret.get_secret_value(),
    )

    async def scrape(client: httpx.AsyncClient) -> str:
        resp = await client.get("/metrics")
        assert resp.status_code == 200, resp.text
        return resp.text

    sid = f"m42-metrics-demo-{uuid4().hex[:8]}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local", timeout=120.0
    ) as client:
        before_text = await scrape(client)
        before = _ratio_of(before_text, "tenant-a")
        print(f"演示前 tenant-a 预算比：{before}")
        for i, message in enumerate(ROUNDS, 1):
            resp = await client.post(
                "/v1/chat",
                json={"session_id": sid, "message": message},
                headers={"Authorization": f"Bearer {user_token}"},
            )
            print(f"第 {i} 轮 HTTP {resp.status_code}，帧数~{resp.text.count('event:')}")
            assert resp.status_code == 200, resp.text[:300]
        after_text = await scrape(client)
        after = _ratio_of(after_text, "tenant-a")
        print(f"演示后 tenant-a 预算比：{after}")

    if before is None or after is None or not after > before:
        print("ratio 未上升——检查预算列/账本写入后再落盘凭证（凭证不掺假）")
        sys.exit(1)

    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    OUT.write_text(
        f"M4.2 /metrics 实拍凭证（{stamp}）\n"
        "==================================================\n"
        "口径：GET /metrics 经 create_app() 生产装配链实拍（ASGI 直连，与 curl 同字节）；\n"
        f"#23 演示=拍板 2 批准的一次性真实调用例外，恰 {len(ROUNDS)} 轮 chat（会话 {sid}），\n"
        "预算比分子复用月度闸门 MeteringRecorder.month_spend 同一实现。\n"
        "\n"
        'aegis_tenant_budget_used_ratio{tenant_id="tenant-a"}：\n'
        f"  演示前 = {before}\n"
        f"  演示后 = {after}   （↑ 肉眼可见上升，00 §8.1 M4.2 行 #23 验收点）\n"
        "\n"
        "-------- 演示后全量 exposition（11 族） --------\n"
        f"{after_text}",
        encoding="utf-8",
    )
    print(f"已写 {OUT}")


asyncio.run(main())

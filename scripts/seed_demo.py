"""演示数据种子（M3.11 正式版：tenants/users + mock_orders + 语料摄取——02 §5「一键重建」口径）。

种子即初始化入口（00 §10.1 #21 / D12 拍板）：tenants.config 运行期只读，
变更 = 改本脚本重跑。全链 upsert 幂等：跑两遍不重复不报错、演示改动重跑即复位
（tests/apps/test_seed_script.py 钉住）。

语料摄取走真实 embedding（M3 真实调用口径 00 §7.0）：全量 20 篇约 1 万 token、
成本 <¥0.02；幂等同时是省钱闸——「原文未变且已 DONE」的文档整篇跳过（零 API 调用），
原文变更才删块重摄取。身份边界（M3.5 偏差(32) 封闭名单「脚本 main」位）：
tenants/users/mock_orders 走 owner 维护面（D4：跨租户初始化不冒充任何租户）；
语料摄取按租户 tenant_context 包全程 + app 引擎（与 worker 任务内胆同构，走 RLS 放行面）。

在仓库根执行（.env 相对 cwd 加载——08 §9.1 运行前提）：

    uv run python scripts/seed_demo.py
"""

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from aegis.apps.support.mock_backend.models import MockOrderRecord
from aegis.apps.support.rag.models import ChunkRecord, DocumentRecord, IngestStatus
from aegis.core.db import get_owner_session_factory, get_session_factory
from aegis.core.tenancy import Role, SessionFactory, TenantRecord, UserRecord
from aegis.core.tenant_ctx import tenant_context
from aegis.gateway.factory import build_embedding_client
from aegis.workers.ingest import EmbedderLike, ingest_once

# 落盘路径锚定项目根（记忆教训：PyCharm cwd=脚本目录，相对路径会读错位置）
ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "data" / "corpus"

# 01 §5 两租户设定；approval_threshold=200 是租户 A 的配置项不是平台常量。
# token_budget_monthly=2_000_000：M3 开发调试走真实调用的月度兜底（plans/m3-detailed §3.1）。
# M3.11 拍板 1：coupon_threshold=50（B 侧 approval_threshold 对应物，超过 50 元的补偿券
#   挂人工审批——语料 coupon-compensation.md 同数字，评测集隔离用例引用同阈值）；
# M3.11 拍板 2：approval_ttl_s 显式落种子=消灭「默认值巧合相等」挂点（08 §8 #10 同族），
#   值取 LoopPolicy 默认 3600，演示超时走时钟注入不靠真实短 TTL（demo_hitl 先例）。
TENANTS: list[dict[str, Any]] = [
    {
        "id": "tenant-a",
        "name": "云杉数码商城",
        "config": {
            "approval_threshold": 200,
            "approval_ttl_s": 3600,
            "tools": ["order_query", "logistics_query", "refund_apply", "ticket_create"],
            "faq": (
                "云杉数码商城常见问题：营业时间 9:00-18:00（周一至周日）；"
                "客服热线 400-800-1234；支持 7 天无理由退货（详情请查询退货政策）。"
            ),
        },
        "token_budget_monthly": 2_000_000,
    },
    {
        "id": "tenant-b",
        "name": "云杉生鲜超市",
        "config": {
            "coupon_threshold": 50,
            "approval_ttl_s": 3600,
            "tools": ["order_query", "coupon_grant"],
            "faq": (
                "云杉生鲜超市常见问题：配送时间每日 8:00-22:00；客服热线 400-800-5678；生鲜商品损坏可申请优惠券补偿。"
            ),
        },
        "token_budget_monthly": 2_000_000,
    },
]

# 每租户 user×2（跨用户订单对抗需要两个）+ operator×1 + admin×1（02 §7.1 三档）
USERS: list[dict[str, Any]] = []
for t in ("a", "b"):
    USERS += [
        {"id": f"u-{t}1", "tenant_id": f"tenant-{t}", "role": Role.USER.value, "display_name": "演示用户一"},
        {"id": f"u-{t}2", "tenant_id": f"tenant-{t}", "role": Role.USER.value, "display_name": "演示用户二"},
        {"id": f"op-{t}1", "tenant_id": f"tenant-{t}", "role": Role.OPERATOR.value, "display_name": "演示坐席"},
        {"id": f"admin-{t}1", "tenant_id": f"tenant-{t}", "role": Role.ADMIN.value, "display_name": "演示管理员"},
    ]

# 演示订单五单（M3.7 拍板Ⅲ「种子订单归 M3.11 正式化」的承接）。覆盖面：
#   AZ-1001 低于 A 阈值 200 → 退款直执；AZ-1002 超阈值 → 挂审批（HITL/cassette 素材）；
#   AZ-2001 属 u-a2 / BF-5002 属 u-b2 → 跨用户对抗靶（对抗③）；
#   BF-5001 45 元 ≤ B 阈值 50 → 补偿券直发；BF-5002 88 元 > 50 → 补偿券挂审批。
# 单号避开演示脚本自清理段（mo-demo-*）与 M2.11 cassette 埋点（AZ-20260701-0042）。
ORDERS: list[dict[str, Any]] = [
    {
        "id": "AZ-1001",
        "tenant_id": "tenant-a",
        "user_id": "u-a1",
        "status": "paid",
        "paid_amount": "168.00",
        "items": {"sku": "灵犀降噪耳机 Pro", "qty": 1},
    },
    {
        "id": "AZ-1002",
        "tenant_id": "tenant-a",
        "user_id": "u-a1",
        "status": "delivered",
        "paid_amount": "599.00",
        "items": {"sku": "R68 Pro", "qty": 1},
    },
    {
        "id": "AZ-2001",
        "tenant_id": "tenant-a",
        "user_id": "u-a2",
        "status": "paid",
        "paid_amount": "259.00",
        "items": {"sku": "R68 Pro", "qty": 1},
    },
    {
        "id": "BF-5001",
        "tenant_id": "tenant-b",
        "user_id": "u-b1",
        "status": "delivered",
        "paid_amount": "45.00",
        "items": {"sku": "有机蔬菜礼盒", "qty": 1},
    },
    {
        "id": "BF-5002",
        "tenant_id": "tenant-b",
        "user_id": "u-b2",
        "status": "delivered",
        "paid_amount": "88.00",
        "items": {"sku": "冰鲜三文鱼", "qty": 2},
    },
]


async def seed_tenants_users(
    factory: SessionFactory,
    *,
    tenants: list[dict[str, Any]] | None = None,
    users: list[dict[str, Any]] | None = None,
) -> None:
    """tenants/users upsert（M3.1 起步版原语义，抽成可注入函数供测试以随机 id 驱动）。"""
    async with factory() as s:
        async with s.begin():
            for row in tenants if tenants is not None else TENANTS:
                stmt = insert(TenantRecord).values(**row)
                await s.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[TenantRecord.id],
                        set_={
                            "name": stmt.excluded.name,
                            "config": stmt.excluded.config,
                            "token_budget_monthly": stmt.excluded.token_budget_monthly,
                        },
                    )
                )
            for row in users if users is not None else USERS:
                stmt = insert(UserRecord).values(**row)
                await s.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[UserRecord.id],
                        set_={
                            "tenant_id": stmt.excluded.tenant_id,
                            "role": stmt.excluded.role,
                            "display_name": stmt.excluded.display_name,
                        },
                    )
                )


async def seed_orders(factory: SessionFactory, *, orders: list[dict[str, Any]] | None = None) -> None:
    """mock_orders upsert：重跑把演示改动（如已退款）复位回种子态——「一键重建」的订单面。

    mock_write_ops 台账不清理：它是 #6 去重的历史事实，新演示用新 tool_call_id 钥匙，
    旧行无害（全局清理是演示脚本 finally 自理的职责，M2.10 教训）。
    """
    async with factory() as s:
        async with s.begin():
            for o in orders if orders is not None else ORDERS:
                stmt = insert(MockOrderRecord).values(
                    id=o["id"],
                    tenant_id=o["tenant_id"],
                    user_id=o["user_id"],
                    status=o["status"],
                    paid_amount=Decimal(o["paid_amount"]),
                    items=o["items"],
                )
                await s.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[MockOrderRecord.id],
                        set_={
                            "tenant_id": stmt.excluded.tenant_id,
                            "user_id": stmt.excluded.user_id,
                            "status": stmt.excluded.status,
                            "paid_amount": stmt.excluded.paid_amount,
                            # 下标形式是刚性要求：excluded.items 命中 ColumnCollection.items() 方法
                            # 而非同名列（拿到 bound method，执行期 JSON 序列化炸）——影子排练实录
                            "items": stmt.excluded["items"],
                        },
                    )
                )


async def seed_corpus_for_tenant(
    factory: SessionFactory,
    embedder: EmbedderLike,
    *,
    tenant_id: str,
    corpus_dir: Path,
) -> tuple[int, int, int]:
    """语料落库+摄取，返回 (新摄取, 续传, 跳过)。调用方负责身份边界（tenant_context）。

    三分支语义（幂等即省钱闸）：
    - 原文未变且已 DONE → 整篇跳过，零 API 调用；
    - 原文未变但未走完（pending/processing/failed）→ 不删块直接 ingest_once：
      续传语义（IS NULL 回填）与 worker 重试进场完全同构；
    - 新文档或原文已变 → upsert 原文+复位 PENDING+删旧块，全新摄取
      （chunk 是原文的派生物，原文换了派生物必须重建——不存在增量补丁）。
    """
    paths = sorted(corpus_dir.glob("*.md"))
    if not paths:
        raise SystemExit(f"语料目录为空：{corpus_dir}（仓库资产缺失，拒绝静默跳过）")
    fresh = resumed = skipped = 0
    for path in paths:
        doc_id = f"{tenant_id}-{path.stem}"
        text_content = path.read_text(encoding="utf-8")
        async with factory() as s:
            row = (await s.execute(select(DocumentRecord).where(DocumentRecord.id == doc_id))).scalar_one_or_none()
            unchanged = row is not None and row.text == text_content
            done = row is not None and row.status == IngestStatus.DONE.value
        if unchanged and done:
            skipped += 1
            continue
        async with factory() as s:
            async with s.begin():
                stmt = insert(DocumentRecord).values(
                    id=doc_id,
                    tenant_id=tenant_id,
                    source=path.name,
                    text=text_content,
                    status=IngestStatus.PENDING.value,
                    meta={},
                )
                await s.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[DocumentRecord.id],
                        set_={
                            "source": stmt.excluded.source,
                            "text": stmt.excluded.text,
                            "status": IngestStatus.PENDING.value,
                            "error": None,
                        },
                    )
                )
                if not unchanged:
                    await s.execute(delete(ChunkRecord).where(ChunkRecord.document_id == doc_id))
        await ingest_once(factory, embedder, document_id=doc_id, tenant_id=tenant_id)
        if unchanged:
            resumed += 1
        else:
            fresh += 1
    return fresh, resumed, skipped


async def main() -> None:
    owner = get_owner_session_factory()
    await seed_tenants_users(owner)
    await seed_orders(owner)

    app_factory = get_session_factory()  # app 引擎+租户钩子；摄取与 worker 内胆同构走 RLS
    embedder = build_embedding_client()  # 单次 asyncio.run 内构造与使用同 loop（M3.4 教训面安全）
    for row in TENANTS:
        tid = str(row["id"])
        with tenant_context(tid):  # 每租户各自建边界（M3.8 幕 C 教训：身份声明是每租户义务）
            fresh, resumed, skipped = await seed_corpus_for_tenant(
                app_factory, embedder, tenant_id=tid, corpus_dir=CORPUS_ROOT / tid
            )
        print(f"语料[{tid}]：新摄取 {fresh} 续传 {resumed} 跳过 {skipped}")

    print(f"种子完成：tenants={len(TENANTS)} users={len(USERS)} orders={len(ORDERS)}（upsert，可重复执行）")


if __name__ == "__main__":
    asyncio.run(main())

"""M3.11 交付①：种子脚本与语料资产契约（importlib 复用脚本本体——I1 单一事实源，M2.11 先例）。

三层判据：
- 资产 lint（零 DB）：语料布局与语义锚——校准脚本/评测集依赖的字面锚点在文件层钉死；
- 常量 lint（零 DB）：拍板 1/2 种子值 + 工具名 ⊆ ALL_TOOLS（装配器「未知名启动炸」的测试前移）；
- 行为（SAVEPOINT 库，owner 连接绕 RLS——test_ingest_resume 同款口径）：三类 upsert 幂等
  与语料摄取生命周期，一律随机 id（M3.10 偏差(52) 硬规则），绝不触碰 tenant-a/b 真实种子行。
"""

from __future__ import annotations

import importlib.util
import uuid
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from sqlalchemy import select, update

from aegis.apps.support.agent import ALL_TOOLS
from aegis.apps.support.mock_backend.models import MockOrderRecord
from aegis.apps.support.rag.models import EMBEDDING_DIMS, ChunkRecord, DocumentRecord, IngestStatus
from aegis.core.tenancy import TenantRecord, UserRecord

ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = ROOT / "data" / "corpus"
_SCRIPT_PATH = ROOT / "scripts" / "seed_demo.py"


@lru_cache(maxsize=1)
def _script() -> ModuleType:
    """经 importlib 装载种子脚本（缓存）：常量与函数的单一事实源，不抄第二份。

    脚本 import 期零副作用（main() 有 __main__ 门、无模块级 IO/网络）。
    """
    spec = importlib.util.spec_from_file_location("seed_demo", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeEmbedder:
    """EmbedderLike 形状替身：记录调用作「跳过=零 API」的证词（test_ingest_resume 同款）。"""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []

    async def embed(self, texts, *, tenant_id: str) -> list[list[float]]:
        self.calls.append((list(texts), tenant_id))
        return [[0.5] * EMBEDDING_DIMS for _ in texts]


def test_corpus_layout_contract() -> None:
    """语料布局：两租户各 ≥10 篇、各含 faq.md（M3.6 后置修订⑶ 守卫补集）、文档 id 不超列宽。"""
    for tid in ("tenant-a", "tenant-b"):
        files = sorted((CORPUS_ROOT / tid).glob("*.md"))
        assert len(files) >= 10, f"{tid} 语料不足 10 篇：{len(files)}"
        assert (CORPUS_ROOT / tid / "faq.md").exists(), f"{tid} 缺 FAQ 文档（守卫补集条件）"
        for f in files:
            assert len(f"{tid}-{f.stem}") <= 64, f"文档 id 超 String(64)：{f.name}"


def test_corpus_semantic_anchors() -> None:
    """语义锚 lint：校准脚本与隔离对抗依赖的字面锚点只许出现在所属租户的语料里。

    - A 含「七天无理由退货」（calibrate 的 A_LITERAL）、退款 200 审批叙述、
      灵犀降噪耳机 Pro + 24 个月（评测集 iso 用例的 must_not_contain 锚）；
    - A 全库不得出现「优惠券」（calibrate OFF_TOPIC「优惠券怎么领取」的不可命中面）；
    - B 含 50 元补偿券审批叙述；B 全库不得出现「七天无理由退货」与「灵犀」（对抗①字面锚）。
    """
    a_all = "".join(p.read_text(encoding="utf-8") for p in sorted((CORPUS_ROOT / "tenant-a").glob("*.md")))
    b_all = "".join(p.read_text(encoding="utf-8") for p in sorted((CORPUS_ROOT / "tenant-b").glob("*.md")))
    assert "七天无理由退货" in a_all
    assert "优惠券" not in a_all, "A 语料出现「优惠券」——calibrate off-topic 判据被污染"
    a_returns = (CORPUS_ROOT / "tenant-a" / "returns-policy.md").read_text(encoding="utf-8")
    assert "200" in a_returns and "审批" in a_returns, "A 退款审批阈值叙述缺失"
    a_warranty = (CORPUS_ROOT / "tenant-a" / "warranty-policy.md").read_text(encoding="utf-8")
    assert "灵犀降噪耳机 Pro" in a_warranty and "24 个月" in a_warranty
    assert "七天无理由退货" not in b_all and "灵犀" not in b_all, "A 专有锚泄入 B 语料——对抗①判据被污染"
    b_coupon = (CORPUS_ROOT / "tenant-b" / "coupon-compensation.md").read_text(encoding="utf-8")
    assert "50" in b_coupon and "审批" in b_coupon, "B 补偿券阈值叙述缺失"


def test_seed_constants_pinned() -> None:
    """拍板 1/2 种子值钉死 + 配置引用的工具名/用户名在货架与名单内（配置错误测试前移）。"""
    seed = _script()
    tenants = {row["id"]: row for row in seed.TENANTS}
    a, b = tenants["tenant-a"]["config"], tenants["tenant-b"]["config"]
    assert a["approval_threshold"] == 200 and a["approval_ttl_s"] == 3600
    assert b["coupon_threshold"] == 50 and b["approval_ttl_s"] == 3600
    for cfg in (a, b):
        assert set(cfg["tools"]) <= set(ALL_TOOLS), f"配置了货架外工具：{set(cfg['tools']) - set(ALL_TOOLS)}"
        assert cfg["faq"], "faq 摘要为空——FAQ 直答分支断粮"
    order_ids = [o["id"] for o in seed.ORDERS]
    assert len(order_ids) == len(set(order_ids)), "订单 id 重复"
    user_ids = {u["id"] for u in seed.USERS}
    for o in seed.ORDERS:
        assert o["tenant_id"] in tenants and o["user_id"] in user_ids, f"订单 {o['id']} 归属指向不存在的租户/用户"


async def test_tenants_users_upsert_idempotent(db_session_factory) -> None:
    """upsert 幂等：二跑走 update 路径不重复不报错，值以最后一跑为准（随机 id 不碰真实种子）。"""
    seed = _script()
    tid = f"t-seed-{uuid.uuid4().hex[:8]}"
    uid = f"u-seed-{uuid.uuid4().hex[:8]}"
    tenants = [{"id": tid, "name": "幂等租户", "config": {"tools": []}, "token_budget_monthly": 1}]
    users = [{"id": uid, "tenant_id": tid, "role": "user", "display_name": "一"}]
    await seed.seed_tenants_users(db_session_factory, tenants=tenants, users=users)
    users[0]["display_name"] = "二"
    await seed.seed_tenants_users(db_session_factory, tenants=tenants, users=users)
    async with db_session_factory() as s:
        t_rows = (await s.execute(select(TenantRecord).where(TenantRecord.id == tid))).scalars().all()
        u_rows = (await s.execute(select(UserRecord).where(UserRecord.id == uid))).scalars().all()
    assert len(t_rows) == 1 and len(u_rows) == 1
    assert u_rows[0].display_name == "二"


async def test_orders_upsert_resets_demo_state(db_session_factory) -> None:
    """订单种子的「一键重建」语义：演示把单退了，重跑种子复位回种子态（恰一行）。"""
    seed = _script()
    oid = f"ord-seed-{uuid.uuid4().hex[:8]}"
    orders = [
        {
            "id": oid,
            "tenant_id": f"t-seed-{uuid.uuid4().hex[:8]}",
            "user_id": "u-x",
            "status": "paid",
            "paid_amount": "88.00",
            "items": {"sku": "演示品"},
        }
    ]
    await seed.seed_orders(db_session_factory, orders=orders)
    async with db_session_factory() as s:
        async with s.begin():
            await s.execute(update(MockOrderRecord).where(MockOrderRecord.id == oid).values(status="refunded"))
    await seed.seed_orders(db_session_factory, orders=orders)
    async with db_session_factory() as s:
        rows = (await s.execute(select(MockOrderRecord).where(MockOrderRecord.id == oid))).scalars().all()
    assert len(rows) == 1 and rows[0].status == "paid"


async def test_seed_corpus_lifecycle(db_session_factory, tmp_path) -> None:
    """语料摄取三分支全谱：新摄取 → 未变跳过（零 API 调用）→ 原文变更删块重摄取。"""
    seed = _script()
    tid = f"t-corpus-{uuid.uuid4().hex[:8]}"
    corpus = tmp_path / tid
    corpus.mkdir()
    (corpus / "faq.md").write_text("# FAQ\n\n营业时间与联系方式。", encoding="utf-8")
    (corpus / "policy.md").write_text("# 政策\n\n退款规则第一版。", encoding="utf-8")
    fake = FakeEmbedder()

    assert await seed.seed_corpus_for_tenant(db_session_factory, fake, tenant_id=tid, corpus_dir=corpus) == (2, 0, 0)
    calls_after_first = len(fake.calls)
    async with db_session_factory() as s:
        docs = (await s.execute(select(DocumentRecord).where(DocumentRecord.tenant_id == tid))).scalars().all()
    assert {d.status for d in docs} == {IngestStatus.DONE.value} and len(docs) == 2

    # 二跑：原文未变且 DONE → 整篇跳过，embedder 一次都不该被叫（幂等即省钱闸）
    assert await seed.seed_corpus_for_tenant(db_session_factory, fake, tenant_id=tid, corpus_dir=corpus) == (0, 0, 2)
    assert len(fake.calls) == calls_after_first

    # 三跑：改一篇原文 → 该篇删块重摄取，另一篇仍跳过；chunk 无残留、向量全在场
    (corpus / "policy.md").write_text("# 政策\n\n退款规则第二版，全文重写。", encoding="utf-8")
    assert await seed.seed_corpus_for_tenant(db_session_factory, fake, tenant_id=tid, corpus_dir=corpus) == (1, 0, 1)
    doc_id = f"{tid}-policy"
    async with db_session_factory() as s:
        doc = (await s.execute(select(DocumentRecord).where(DocumentRecord.id == doc_id))).scalar_one()
        chunks = (
            (await s.execute(select(ChunkRecord).where(ChunkRecord.document_id == doc_id).order_by(ChunkRecord.seq)))
            .scalars()
            .all()
        )
    assert "第二版" in doc.text and doc.status == IngestStatus.DONE.value
    assert [c.seq for c in chunks] == list(range(len(chunks))) and len(chunks) == doc.chunk_count
    assert all(c.embedding is not None and "第一版" not in c.text for c in chunks)

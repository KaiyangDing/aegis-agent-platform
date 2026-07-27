"""检索阈值校准：RETRIEVAL_SCORE_THRESHOLD 真实语料实测（M3.5④，plans/m3-detailed §3.5）。

仓库根执行（.env 相对 cwd）：
    uv run python scripts/calibrate_retrieval_threshold.py

真实调用口径：M3 开发调试允许（00 §7.0）；成本上限由查询清单钉死——
6 次 embedding、每次 ≤20 token，<¥0.0002；CI 不跑本脚本（scripts/ 不在 pytest 收集面）。
判定谓词与生产同式（all(score < 阈值)，单测已钉）；threshold=0.0 实例只为观察原始分。
首轮实测 2026-07-25（tenant-a returns-demo.md 1 块语料）：on-topic 三条 0.45–0.60 全命中、
off-topic 两条 0.19/0.31 全拒答（「优惠券」sim=0.45 被 0.7 权重压回——重排的直接战果）、
B 租户查 A 专有短语空集（对抗①真实链路）；分离窗 [0.31, 0.45] 含 0.35 → 维持占位值。

**B 检判据修订（2026-07-27，M3.11 扩容复核实录）**：首测世界 B 是空库，「空集」是廉价判据；
扩容后 B 有自家售后语料，threshold=0 观察位对 A 短语必然返回 top-5 的 B 自家块
（WHERE+RLS 结构保证只可能是 B 块）——空集不再是对抗①的判据。扩容后口径=**字面核证**：
①命中文本零 A 专有字面（真泄漏面）；②过生产阈值条数如实报告（B 用户问退货命中
B 自家售后政策是合法行为，不是泄漏）。
二轮实测 2026-07-27（A 21 块 / B 10 块）：on-topic 0.45–0.69 全命中、off-topic 0.209/0.334
全拒答，分离窗收窄至 [0.334, 0.452] 仍含 0.35 → **维持**（「优惠券」0.334 距阈 0.016，
M4.5 扩集时留意）；B 检零 A 字面有语料 lint 结构保证（test_corpus_semantic_anchors），
过阈值条数以复跑输出为准。
"""

import asyncio

from aegis.apps.support.rag.retrieve import RETRIEVAL_SCORE_THRESHOLD, Retriever
from aegis.core.db import get_session_factory
from aegis.core.tenant_ctx import tenant_context
from aegis.gateway.factory import build_embedding_client

ON_TOPIC = ["如何申请退货？", "退款多久能到账", "生鲜商品能不能退"]
OFF_TOPIC = ["今天天气怎么样", "优惠券怎么领取"]
A_LITERAL = "七天无理由退货"  # A 语料字面短语——租户 B 侧对抗查询


async def main() -> None:
    factory = get_session_factory()  # app 引擎+租户钩子；身份由本脚本 main 建边界
    embedder = build_embedding_client()
    raw = Retriever(factory, embedder, threshold=0.0)

    print(f"阈值 = {RETRIEVAL_SCORE_THRESHOLD}；语料以库内实际为准（M3.5 首测：tenant-a 1 块）\n")
    with tenant_context("tenant-a"):
        for q in ON_TOPIC + OFF_TOPIC:
            hits = await raw.search("tenant-a", q)
            rejected = all(h.score < RETRIEVAL_SCORE_THRESHOLD for h in hits)
            top = f"sim={hits[0].similarity:.4f} score={hits[0].score:.4f}" if hits else "无候选"
            expect = "期望命中" if q in ON_TOPIC else "期望拒答"
            print(f"[A] {q}: top1 {top} → 判定 {'拒答(空)' if rejected else '命中'}（{expect}）")

    with tenant_context("tenant-b"):
        b_hits = await raw.search("tenant-b", A_LITERAL)
        passing = [h for h in b_hits if h.score >= RETRIEVAL_SCORE_THRESHOLD]
        leaked = [h for h in b_hits if A_LITERAL in h.text]
        print(f"\n[B] 用 A 专有短语「{A_LITERAL}」查询租户 B：")
        for h in b_hits:
            print(f"    {h.document_id}  sim={h.similarity:.4f} score={h.score:.4f}")
        print(f"    候选 {len(b_hits)} 条（threshold=0 观察位，结构上只能是 B 自家块）；过生产阈值 {len(passing)} 条")
        if leaked:
            print(f"    异常！A 字面泄入 B 命中文本 {len(leaked)} 条——隔离被穿，立刻排查")
        else:
            print("    命中文本零 A 字面（对抗①字面核证 ✓；B 语义近邻命中自家售后语料属合法行为）")


if __name__ == "__main__":
    asyncio.run(main())

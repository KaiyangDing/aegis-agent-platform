"""多租户向量检索（M3.5 交付②，plans/m3-detailed §4.5 / ADR-006 / 00 §7.1 M3.5 行）。

隔离两层表述（ADR-006，面试考点）：
- 越权隔离=硬保证：SQL 显式 WHERE tenant_id（应用层第一防线）+ RLS 兜底（第二防线），
  绝不"反正有 RLS"（02 §7.2）；
- 召回完整性=质量保证：HNSW 带 WHERE 是索引内后过滤，命中不足会漏召回——小租户
  直接精确扫描（万级全扫既正确又够快，租户规模设定 01 §5 使备选即主选合法），
  大租户 hnsw.iterative_scan=relaxed_order 迭代补扫（pgvector ≥0.8.0）。

本文件是检索唯一入口（<=> 算子只许在此出现）；rerank 是模块边界（换 cross-encoder
不动本文件）。失败语义 fail-loud：embedder/DB 异常裸抛——增强层的 fail-open 归
槽位适配器（交付③，#42 修案 (a)），领域对象不吞错，评测与演示需要诚实的失败。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Protocol

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from aegis.apps.support.rag.models import ChunkRecord
from aegis.apps.support.rag.rerank import RetrievedChunk, rerank
from aegis.core.tenancy import SessionFactory
from aegis.core.tenant_ctx import tenant_context

RETRIEVAL_SCORE_THRESHOLD = 0.35
"""综合分下限（相似度语义，不是距离）。§3.5 留白占位，交付④真语料实测校准。"""

EXACT_SCAN_MAX_CHUNKS = 10_000
"""精确扫描上限：租户 chunk 数 ≤ 此值走全表精确扫。§3.5 留白，同上。"""

_COUNT_CACHE_TTL_S = 60.0
"""租户计数缓存 TTL（TenantDirectory 60s 同款）：扫描模式判定容忍一分钟陈旧——
错判一档只影响召回质量微差，不碰正确性与隔离。"""

_CANDIDATE_MULTIPLIER = 3
"""候选池倍率：取 3×top_k 喂重排（§4.5 第 4 步）——池只有 top_k 大，重排无从反超。"""

# 裸 SQL 口径（00 §2.2 + models.py:70 预告）。CAST(:qvec AS vector)：向量以 pgvector
# 文本形态 "[x,y,...]" 传参——asyncpg 只认 $n 占位，具名绑定走编译层（M3.3 偏差⑿同族）；
# <=> 是余弦距离（0=同向），1-距离=相似度（§4.5 陷阱 3：拿距离当相似度比阈值必翻车）。
_SEARCH_SQL = text(
    "SELECT id, document_id, text, meta,"
    " 1 - (embedding <=> CAST(:qvec AS vector)) AS similarity"
    " FROM chunks"
    " WHERE tenant_id = :tid AND embedding IS NOT NULL"
    " ORDER BY embedding <=> CAST(:qvec AS vector)"
    " LIMIT :lim"
)

_SET_EXACT_SCAN = text("SET LOCAL enable_indexscan = off")
_SET_ITERATIVE_SCAN = text("SET LOCAL hnsw.iterative_scan = relaxed_order")


class EmbedderLike(Protocol):
    """查询向量化面按形状注入（EmbeddingClient.embed 形状）——workers/ingest.py:39
    同款本层副本：apps 不许向上 import workers（层契约），测试替身不背真通道。"""

    async def embed(self, texts: Sequence[str], *, tenant_id: str) -> list[list[float]]: ...


def _vector_literal(vec: Sequence[float]) -> str:
    """pgvector 文本形态 "[0.1,0.2,...]"（输入解析接受科学计数法，str() 即可）。"""
    return "[" + ",".join(map(str, vec)) + "]"


class Retriever:
    """六步：向量化 → 租户计数（缓存）→ 扫描模式 → 距离查询 → 重排 → 阈值兜底。"""

    def __init__(
        self,
        factory: SessionFactory,
        embedder: EmbedderLike,
        *,
        top_k: int = 5,
        threshold: float = RETRIEVAL_SCORE_THRESHOLD,
        exact_scan_max_chunks: int = EXACT_SCAN_MAX_CHUNKS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._factory = factory
        self._embedder = embedder
        self._top_k = top_k
        self._threshold = threshold
        self._exact_scan_max_chunks = exact_scan_max_chunks  # 注入缝：测试免搬一万行
        self._clock = clock  # TenantDirectory 同款：TTL 测试不睡真钟
        self._count_cache: dict[str, tuple[int, float]] = {}  # tenant_id -> (count, 存入时刻)

    async def search(self, tenant_id: str, query: str) -> list[RetrievedChunk]:
        """空列表 = 检索失败（无语料/全低于阈值）——调用方走兜底话术，宁可说不知道。"""
        [qvec] = await self._embedder.embed([query], tenant_id=tenant_id)  # 网络慢活在事务外
        with tenant_context(tenant_id):  # 冒充租户过 RLS（app 引擎钩子读它——D4 对偶）
            async with self._factory() as s:
                async with s.begin():
                    count = await self._tenant_chunk_count(s, tenant_id)
                    scan = _SET_EXACT_SCAN if count <= self._exact_scan_max_chunks else _SET_ITERATIVE_SCAN
                    await s.execute(scan)  # SET LOCAL 事务级：与查询同事务才生效（§4.5 陷阱 4）
                    rows = (
                        await s.execute(
                            _SEARCH_SQL,
                            {
                                "qvec": _vector_literal(qvec),
                                "tid": tenant_id,
                                "lim": self._top_k * _CANDIDATE_MULTIPLIER,
                            },
                        )
                    ).all()
        hits = [
            RetrievedChunk(
                chunk_id=row.id,
                document_id=row.document_id,
                text=row.text,
                similarity=float(row.similarity),  # pgvector float32 存储：读回带 ~1e-8 噪音
                meta=row.meta,
            )
            for row in rows
        ]
        ranked = rerank(query, hits)[: self._top_k]
        if all(h.score < self._threshold for h in ranked):  # 空池 all()=True，天然归入检索失败
            return []
        return ranked

    async def _tenant_chunk_count(self, s: AsyncSession, tenant_id: str) -> int:
        """租户全量 chunk 计数，进程内 60s 缓存——只服务扫描模式判定，不追新鲜。"""
        now = self._clock()
        cached = self._count_cache.get(tenant_id)
        if cached is not None and now - cached[1] < _COUNT_CACHE_TTL_S:
            return cached[0]
        count = (
            await s.execute(select(func.count()).select_from(ChunkRecord).where(ChunkRecord.tenant_id == tenant_id))
        ).scalar_one()
        self._count_cache[tenant_id] = (count, now)
        return count

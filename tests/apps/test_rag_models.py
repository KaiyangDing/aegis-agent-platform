"""M3.4 交付①：知识库两表 ORM——P6 拆表口径的行为面（SAVEPOINT 夹具，owner 连接绕 RLS）。

RLS/策略/HNSW 等迁移工件断言在 tests/test_rls.py 的 M3.4 增量节（真提交语义那边才看得见）；
本文件只管 ORM 语义：vector 往返、IS NULL 续传谓词、UNIQUE(document_id, seq) 幂等锚。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from aegis.apps.support.rag.models import (
    EMBEDDING_DIMS,
    ChunkRecord,
    DocumentRecord,
    IngestStatus,
)


def test_ingest_status_values_are_stable() -> None:
    """四态值快照：status 列存 .value，API（202 返回体）与任务（状态机推进）两端都读它——改值=破坏历史行。"""
    assert {s.value for s in IngestStatus} == {"pending", "processing", "done", "failed"}
    assert len(IngestStatus) == 4


async def test_document_row_roundtrip(db_session_factory) -> None:
    """文档级事实归 documents：meta JSONB 原样往返、chunk_count ORM 默认 0、时间戳 DB 钟（server_default）。"""
    async with db_session_factory() as s:
        async with s.begin():
            s.add(
                DocumentRecord(
                    id="doc-rt",
                    tenant_id="t-rag-rt",
                    source="faq.md",
                    status=IngestStatus.PENDING.value,
                    meta={"lang": "zh"},
                )
            )
    async with db_session_factory() as s:
        row = (await s.execute(select(DocumentRecord).where(DocumentRecord.id == "doc-rt"))).scalar_one()
    assert row.status == "pending"
    assert row.chunk_count == 0
    assert row.error is None
    assert row.meta == {"lang": "zh"}
    assert row.created_at is not None and row.updated_at is not None


async def test_chunk_vector_roundtrip(db_session_factory) -> None:
    """vector(1024)：写入 list[float]、读回 list[float] 逐元素 approx 等值（float32 最短往返误差 ≪ 容差）。"""
    vec = [i / EMBEDDING_DIMS for i in range(EMBEDDING_DIMS)]
    async with db_session_factory() as s:
        async with s.begin():
            s.add(
                ChunkRecord(
                    document_id="doc-vec",
                    tenant_id="t-rag-vec",
                    seq=0,
                    text="向量往返",
                    embedding=vec,
                    embedding_model="text-embedding-v4",
                    meta={},
                )
            )
    async with db_session_factory() as s:
        row = (await s.execute(select(ChunkRecord).where(ChunkRecord.document_id == "doc-vec"))).scalar_one()
    assert len(row.embedding) == EMBEDDING_DIMS
    assert [float(x) for x in row.embedding] == pytest.approx(vec)
    assert row.embedding_model == "text-embedding-v4"


async def test_is_null_predicate_tracks_backfill(db_session_factory) -> None:
    """断点续传的锚：embedding IS NULL 捞活、回填后自然出队——重试不重跑已回填行（§4.4 步骤 3）。"""
    async with db_session_factory() as s:
        async with s.begin():
            s.add_all(
                [
                    ChunkRecord(document_id="doc-null", tenant_id="t", seq=0, text="未回填", meta={}),
                    ChunkRecord(
                        document_id="doc-null",
                        tenant_id="t",
                        seq=1,
                        text="已回填",
                        embedding=[0.5] * EMBEDDING_DIMS,
                        embedding_model="text-embedding-v4",
                        meta={},
                    ),
                ]
            )
    pending_stmt = (
        select(ChunkRecord.seq)
        .where(ChunkRecord.document_id == "doc-null", ChunkRecord.embedding.is_(None))
        .order_by(ChunkRecord.seq)
    )
    async with db_session_factory() as s:
        assert list((await s.execute(pending_stmt)).scalars().all()) == [0]
    async with db_session_factory() as s:
        async with s.begin():
            row = (
                await s.execute(select(ChunkRecord).where(ChunkRecord.document_id == "doc-null", ChunkRecord.seq == 0))
            ).scalar_one()
            row.embedding = [0.25] * EMBEDDING_DIMS
            row.embedding_model = "text-embedding-v4"
    async with db_session_factory() as s:
        assert list((await s.execute(pending_stmt)).scalars().all()) == []


async def test_chunk_seq_unique_per_document(db_session_factory) -> None:
    """UNIQUE(document_id, seq)：切块重试/并发重复投递被数据库兜底；不同文档同 seq 互不干涉。"""

    def make(doc: str) -> ChunkRecord:
        return ChunkRecord(document_id=doc, tenant_id="t", seq=0, text="块", meta={})

    async with db_session_factory() as s:
        async with s.begin():
            s.add(make("doc-uq"))
    with pytest.raises(IntegrityError):
        async with db_session_factory() as s:
            async with s.begin():
                s.add(make("doc-uq"))
    async with db_session_factory() as s:
        async with s.begin():
            s.add(make("doc-uq-other"))

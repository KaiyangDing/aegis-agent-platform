"""摄取流水线 Celery 任务（M3.4 交付③）：切块 → 批量向量化回填 → 终局，断点续传。

薄同步壳 + async 内核（reaper 3.2#7 同款）：ingest_once 依赖全注入、直测零 broker；
@task 壳只做 asyncio.run + 重试/终局。三条防炸前提（plans 14d ②收口钉死）：
⑴ 每任务 NullPool 独立引擎（asyncio.run 每次新 loop，asyncpg 连接绑创建时的 loop），
   且连 database_url_app + install_tenant_guard——逐租户任务冒充租户走 RLS
   （与 reaper 的 owner 维护面成对偶，D4）；
⑵ 任务局部 httpx.AsyncClient 与任务局部 session_factory 双传 build_embedding_client
   （shared_client 的 keep-alive 同绑旧 loop——②校验 major 的实证结论）；
⑶ 任务体全程 tenant_context(tenant_id)——#18 在此闭合；不设则写路径被 RLS 拒、
   计量行被 WITH CHECK 拒再被 fail-open 吞。
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aegis.apps.support.rag.ingest import INGEST_TASK_NAME, split_text
from aegis.apps.support.rag.models import ChunkRecord, DocumentRecord, IngestStatus
from aegis.core.config import get_settings
from aegis.core.tenancy import SessionFactory
from aegis.core.tenant_ctx import install_tenant_guard, tenant_context
from aegis.gateway.embeddings import EMBED_BATCH_SIZE
from aegis.gateway.factory import build_embedding_client
from aegis.gateway.providers.base import sanitize_error_text
from aegis.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class EmbedderLike(Protocol):
    """向量化面按形状注入（EmbeddingClient.embed 的形状）——测试替身不背真通道。"""

    async def embed(self, texts: Sequence[str], *, tenant_id: str) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class IngestReport:
    """一次运行的账目：total=文档现有块数 / embedded=本次回填数（续传时 < total）。"""

    document_id: str
    chunks_total: int
    chunks_embedded: int
    status: str


async def ingest_once(
    factory: SessionFactory,
    embedder: EmbedderLike,
    *,
    document_id: str,
    tenant_id: str,
    batch_size: int = EMBED_BATCH_SIZE,
    embedding_model: str = "text-embedding-v4",
) -> IngestReport:
    """四步：PROCESSING → 切块（幂等）→ IS NULL 批量回填 → DONE。

    断点续传的全部实现＝步骤③的 IS NULL 谓词：重试进场时已回填行天然出队
    （交付①的可空列设计在此兑现），每批独立事务提交——一批失败只丢当批。
    本函数不管终局 FAILED：那是壳在 max_retries 耗尽时的职责（状态是进度
    不是心跳，重试期间不回摆）。依赖全注入、直测零 broker（reaper 同款）。
    """
    # ① 置 PROCESSING、取原文（同一事务；重试进场重置同值——幂等）
    async with factory() as s:
        async with s.begin():
            doc = (await s.execute(select(DocumentRecord).where(DocumentRecord.id == document_id))).scalar_one_or_none()
            if doc is None:
                raise LookupError(f"document 不存在或不属本租户（RLS 视野）：{document_id}")
            doc.status = IngestStatus.PROCESSING.value
            text = doc.text

    # ② 切块幂等：已有行=上次已切完（切块整批同事务原子落库），跳过；UNIQUE 兜底并发重复
    async with factory() as s:
        try:
            async with s.begin():
                existing = (
                    await s.execute(
                        select(func.count()).select_from(ChunkRecord).where(ChunkRecord.document_id == document_id)
                    )
                ).scalar_one()
                if existing == 0:
                    s.add_all(
                        ChunkRecord(document_id=document_id, tenant_id=tenant_id, seq=i, text=piece, meta={})
                        for i, piece in enumerate(split_text(text))
                    )
        except IntegrityError:
            pass  # 并发对手先切完（uq_chunks_document_seq 幂等锚）——直接进回填

    # ③ 回填循环：IS NULL 捞活、每批独立事务、空集即毕
    embedded = 0
    while True:
        async with factory() as s:
            rows = (
                await s.execute(
                    select(ChunkRecord.id, ChunkRecord.text)
                    .where(ChunkRecord.document_id == document_id, ChunkRecord.embedding.is_(None))
                    .order_by(ChunkRecord.seq)
                    .limit(batch_size)
                )
            ).all()
        if not rows:
            break
        vectors = await embedder.embed([r.text for r in rows], tenant_id=tenant_id)
        async with factory() as s:
            async with s.begin():
                for row, vec in zip(rows, vectors, strict=True):
                    await s.execute(
                        update(ChunkRecord)
                        .where(ChunkRecord.id == row.id)
                        .values(embedding=vec, embedding_model=embedding_model)
                    )
        embedded += len(rows)

    # ④ 终局 DONE + chunk_count（error 置空：FAILED 后重投成功的自愈路径不留旧死因）
    async with factory() as s:
        async with s.begin():
            total = (
                await s.execute(
                    select(func.count()).select_from(ChunkRecord).where(ChunkRecord.document_id == document_id)
                )
            ).scalar_one()
            await s.execute(
                update(DocumentRecord)
                .where(DocumentRecord.id == document_id)
                .values(status=IngestStatus.DONE.value, chunk_count=total, error=None)
            )
    return IngestReport(
        document_id=document_id, chunks_total=total, chunks_embedded=embedded, status=IngestStatus.DONE.value
    )


async def mark_failed(factory: SessionFactory, *, document_id: str, error_text: str) -> None:
    """终局 FAILED + 死因落列（error 文本调用方先消毒——源头打码纪律）。"""
    async with factory() as s:
        async with s.begin():
            await s.execute(
                update(DocumentRecord)
                .where(DocumentRecord.id == document_id)
                .values(status=IngestStatus.FAILED.value, error=error_text)
            )


async def _ingest_fresh(document_id: str, tenant_id: str) -> IngestReport:
    """壳的 async 内胆：三条防炸前提的兑现现场（模块 docstring ⑴⑵⑶）。"""
    engine = create_async_engine(get_settings().database_url_app, poolclass=NullPool)
    install_tenant_guard(engine)
    http = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),  # 与 shared_client 同参（base.py:46）
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),  # 任务内批间串行，小池即可
    )
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        embedder = build_embedding_client(session_factory=factory, client=http)
        with tenant_context(tenant_id):
            return await ingest_once(factory, embedder, document_id=document_id, tenant_id=tenant_id)
    finally:
        await http.aclose()
        await engine.dispose()


async def _mark_failed_fresh(document_id: str, tenant_id: str, error_text: str) -> None:
    engine = create_async_engine(get_settings().database_url_app, poolclass=NullPool)
    install_tenant_guard(engine)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        with tenant_context(tenant_id):
            await mark_failed(factory, document_id=document_id, error_text=error_text)
    finally:
        await engine.dispose()


@celery_app.task(name=INGEST_TASK_NAME, bind=True, max_retries=5)
def ingest_document(self, document_id: str, tenant_id: str) -> dict[str, object]:
    """薄同步壳：asyncio.run + 指数退避重试 + 终局。参数只有两个 id——原文在库（偏差(23)）。"""
    try:
        report = asyncio.run(_ingest_fresh(document_id, tenant_id))
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            error_text = sanitize_error_text(f"{type(exc).__name__}: {exc}")
            try:
                asyncio.run(_mark_failed_fresh(document_id, tenant_id, error_text))
            except Exception:
                logger.exception("FAILED 终局落库失败（死因照抛）：document=%s", document_id)
            raise
        raise self.retry(exc=exc, countdown=2.0**self.request.retries) from exc
    logger.info(
        "摄取完成：document=%s chunks=%d embedded=%d",
        report.document_id,
        report.chunks_total,
        report.chunks_embedded,
    )
    return {"document_id": report.document_id, "chunks": report.chunks_total, "embedded": report.chunks_embedded}

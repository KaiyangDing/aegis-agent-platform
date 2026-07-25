"""M3.4 交付③：摄取任务 async 内核——断点续传/幂等/终局（直测零 broker，reaper 同款形态）。

判据全落在库行为上：IS NULL 谓词是续传的全部实现（①的列设计在此兑现），
FakeEmbedder 记录调用作"只补 NULL"的证词。SAVEPOINT 夹具（owner 连接）绕 RLS——
租户上下文/RLS 面在 tests/test_rls.py 与交付④真实链路验收，本文件只管任务语义。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from aegis.apps.support.rag.ingest import INGEST_TASK_NAME
from aegis.apps.support.rag.models import (
    EMBEDDING_DIMS,
    ChunkRecord,
    DocumentRecord,
    IngestStatus,
)
from aegis.workers.celery_app import celery_app
from aegis.workers.ingest import ingest_once, mark_failed


class FakeEmbedder:
    """按 EmbedderLike 形状的替身：记录每次调用，可注入"第 N 次调用炸"。"""

    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.calls: list[tuple[list[str], str]] = []
        self._fail_on = fail_on_call

    async def embed(self, texts, *, tenant_id: str) -> list[list[float]]:
        self.calls.append((list(texts), tenant_id))
        if self._fail_on is not None and len(self.calls) == self._fail_on:
            raise RuntimeError("注入的一批失败")
        return [[0.5] * EMBEDDING_DIMS for _ in texts]


async def _seed_doc(factory, *, doc_id: str, text: str = "", status: str = "pending") -> None:
    async with factory() as s:
        async with s.begin():
            s.add(DocumentRecord(id=doc_id, tenant_id="t-ing", source="seed.md", status=status, text=text, meta={}))


async def _seed_chunk(factory, *, doc_id: str, seq: int, embedded: bool) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(
                ChunkRecord(
                    document_id=doc_id,
                    tenant_id="t-ing",
                    seq=seq,
                    text=f"块{seq}",
                    embedding=[0.9] * EMBEDDING_DIMS if embedded else None,
                    embedding_model="text-embedding-v4" if embedded else None,
                    meta={},
                )
            )


async def _doc(factory, doc_id: str) -> DocumentRecord:
    async with factory() as s:
        return (await s.execute(select(DocumentRecord).where(DocumentRecord.id == doc_id))).scalar_one()


async def _chunks(factory, doc_id: str) -> list[ChunkRecord]:
    async with factory() as s:
        rows = await s.execute(select(ChunkRecord).where(ChunkRecord.document_id == doc_id).order_by(ChunkRecord.seq))
        return list(rows.scalars().all())


def test_task_name_wired_on_both_ends() -> None:
    """wire 契约（决策 A）：apps 侧常量 == workers 侧注册名——api 侧 send_task 凭同一常量点名。"""
    import aegis.workers.ingest  # noqa: F401  # 触发任务注册（worker 进程由 include 完成同一件事）

    assert INGEST_TASK_NAME == "aegis.ingest_document"
    assert INGEST_TASK_NAME in celery_app.tasks
    # include 是 worker 进程装载本模块的唯一链接点（无 beat 条目可锚）——漏改=deploy 哑火而测试全绿
    assert "aegis.workers.ingest" in celery_app.conf.include


async def test_full_run_splits_embeds_and_marks_done(db_session_factory) -> None:
    """全程四步：切块落库（embedding=NULL）→ 按批回填 → DONE + chunk_count。"""
    text = "\n\n".join("文" * 350 for _ in range(3))  # 3 段各 350 token → 恰 3 块（400 预算下互不合并）
    await _seed_doc(db_session_factory, doc_id="d-ing-full", text=text)
    fake = FakeEmbedder()
    report = await ingest_once(db_session_factory, fake, document_id="d-ing-full", tenant_id="t-ing", batch_size=2)
    assert [len(texts) for texts, _ in fake.calls] == [2, 1]  # ≤batch_size 一批、批间串行
    assert {tid for _, tid in fake.calls} == {"t-ing"}
    chunks = await _chunks(db_session_factory, "d-ing-full")
    assert [c.seq for c in chunks] == [0, 1, 2]
    assert all(c.embedding is not None and c.embedding_model == "text-embedding-v4" for c in chunks)
    doc = await _doc(db_session_factory, "d-ing-full")
    assert (doc.status, doc.chunk_count) == (IngestStatus.DONE.value, 3)
    assert (report.chunks_total, report.chunks_embedded, report.status) == (3, 3, "done")


async def test_resume_only_backfills_null_rows(db_session_factory) -> None:
    """断点续传本体：IS NULL 谓词捞活——已回填行绝不重发，向量原值保全。"""
    await _seed_doc(db_session_factory, doc_id="d-ing-res", text="占位", status="processing")
    for seq, embedded in ((0, True), (1, False), (2, True), (3, False)):
        await _seed_chunk(db_session_factory, doc_id="d-ing-res", seq=seq, embedded=embedded)
    fake = FakeEmbedder()
    await ingest_once(db_session_factory, fake, document_id="d-ing-res", tenant_id="t-ing")
    assert fake.calls == [(["块1", "块3"], "t-ing")]  # 只有 NULL 两行、按 seq 序、一批装下
    chunks = await _chunks(db_session_factory, "d-ing-res")
    e0, e1 = chunks[0].embedding, chunks[1].embedding
    assert e0 is not None and e1 is not None  # 先窄化再下标：列类型是 list[float] | None（mypy 四门）
    assert float(e0[0]) == pytest.approx(0.9)  # 已回填行未被重写
    assert float(e1[0]) == pytest.approx(0.5)  # 新回填行是本次值
    assert (await _doc(db_session_factory, "d-ing-res")).status == IngestStatus.DONE.value


async def test_batch_failure_keeps_committed_progress(db_session_factory) -> None:
    """一批失败不重跑全量：已回填批次独立事务已提交；状态停在 PROCESSING（终局归壳）。"""
    await _seed_doc(db_session_factory, doc_id="d-ing-fail", text="占位", status="processing")
    for seq in range(3):
        await _seed_chunk(db_session_factory, doc_id="d-ing-fail", seq=seq, embedded=False)
    fake = FakeEmbedder(fail_on_call=2)
    with pytest.raises(RuntimeError):
        await ingest_once(db_session_factory, fake, document_id="d-ing-fail", tenant_id="t-ing", batch_size=2)
    chunks = await _chunks(db_session_factory, "d-ing-fail")
    assert [c.embedding is not None for c in chunks] == [True, True, False]  # 第一批已落、第二批没到
    assert (await _doc(db_session_factory, "d-ing-fail")).status == IngestStatus.PROCESSING.value


async def test_rerun_when_all_embedded_is_noop_done(db_session_factory) -> None:
    """全量已回填的重投=纯幂等：零 embed 调用、直落 DONE（重试/重投安全的上界证词）。"""
    await _seed_doc(db_session_factory, doc_id="d-ing-noop", text="占位", status="processing")
    for seq in range(2):
        await _seed_chunk(db_session_factory, doc_id="d-ing-noop", seq=seq, embedded=True)
    fake = FakeEmbedder()
    report = await ingest_once(db_session_factory, fake, document_id="d-ing-noop", tenant_id="t-ing")
    assert fake.calls == []
    assert (report.chunks_total, report.chunks_embedded) == (2, 0)
    assert (await _doc(db_session_factory, "d-ing-noop")).status == IngestStatus.DONE.value


async def test_empty_document_goes_done_with_zero_chunks(db_session_factory) -> None:
    """空文档合法：零块零调用，直落 DONE chunk_count=0（上游不拦空文本时的兜底语义）。"""
    await _seed_doc(db_session_factory, doc_id="d-ing-empty", text="")
    fake = FakeEmbedder()
    await ingest_once(db_session_factory, fake, document_id="d-ing-empty", tenant_id="t-ing")
    assert fake.calls == []
    doc = await _doc(db_session_factory, "d-ing-empty")
    assert (doc.status, doc.chunk_count) == (IngestStatus.DONE.value, 0)


async def test_missing_document_raises_lookup_error(db_session_factory) -> None:
    """行不存在（坏 id 或 RLS 视野外）＝调度错误不是暂态故障：LookupError fail-loud。"""
    with pytest.raises(LookupError):
        await ingest_once(db_session_factory, FakeEmbedder(), document_id="d-ing-ghost", tenant_id="t-ing")


async def test_mark_failed_writes_terminal_state(db_session_factory) -> None:
    """终局 FAILED：max_retries 耗尽时壳调用的落库面——status+error 双列。"""
    await _seed_doc(db_session_factory, doc_id="d-ing-dead", text="占位", status="processing")
    await mark_failed(db_session_factory, document_id="d-ing-dead", error_text="RuntimeError: 注入的一批失败")
    doc = await _doc(db_session_factory, "d-ing-dead")
    assert doc.status == IngestStatus.FAILED.value
    assert doc.error == "RuntimeError: 注入的一批失败"

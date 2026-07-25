"""M3.5 交付②③：Retriever 六步算法 + 槽位适配器（真 PG 集成；假 embedder 注入固定向量）。

租户/文档 id 全部随机重绑定（偏差(28) 教训：库内演示残留不许进断言视野）。
向量用单位轴构造——余弦相似度可心算（同轴=1、正交=0、混轴=分量值）。
pgvector 存储是 float32：similarity 断言一律 pytest.approx（交付②前置
实证：0.6 回读 0.6000000238，~1e-8 噪音），不做精确比较。
SET 语句断言用连接级 before_cursor_execute 捕获（同实证钉过可行）。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from aegis.apps.support.rag.models import EMBEDDING_DIMS, ChunkRecord
from aegis.apps.support.rag.retrieve import RetrievalProvider, Retriever
from aegis.core.tenancy import SessionFactory
from aegis.runtime.context import _RETRIEVAL_HEADER, ContextBuilder, RetrievalProviderLike, ScoredSnippet
from aegis.runtime.guardrails import wrap_untrusted
from aegis.runtime.spec import ContextConfig

_SUF = uuid.uuid4().hex[:8]
TEN_A = f"ret-a-{_SUF}"
TEN_B = f"ret-b-{_SUF}"
DOC = f"d-{_SUF}"


def _vec(*components: tuple[int, float]) -> list[float]:
    """稀疏构造 1024 维向量：[(轴, 分量), ...]，其余全零。"""
    v = [0.0] * EMBEDDING_DIMS
    for axis, value in components:
        v[axis] = value
    return v


class _FixedEmbedder:
    """query 文本 → 预置向量（EmbedderLike 形状替身，不背真通道）。"""

    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self._mapping = mapping

    async def embed(self, texts: Sequence[str], *, tenant_id: str) -> list[list[float]]:
        return [self._mapping[t] for t in texts]


class _FakeClock:
    """可推进的单调钟（TenantDirectory 测试同款思路）：TTL 测试不睡真钟。"""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@contextmanager
def _sql_spy(conn) -> Iterator[list[str]]:
    """捕获经该连接下发的 SQL 文本——SET LOCAL 断言的事件口（连接级监听，用毕拆除）。"""
    captured: list[str] = []

    def spy(conn_, cursor, statement, parameters, context, executemany) -> None:
        captured.append(statement)

    event.listen(conn.sync_connection, "before_cursor_execute", spy)
    try:
        yield captured
    finally:
        event.remove(conn.sync_connection, "before_cursor_execute", spy)


async def _add_chunk(
    factory: SessionFactory,
    *,
    tenant_id: str,
    seq: int,
    text_: str,
    embedding: list[float] | None,
    doc: str = DOC,
    meta: dict[str, object] | None = None,
) -> int:
    async with factory() as s:
        async with s.begin():
            rec = ChunkRecord(
                document_id=doc, tenant_id=tenant_id, seq=seq, text=text_, embedding=embedding, meta=meta or {}
            )
            s.add(rec)
            await s.flush()
            return rec.id


async def test_cross_tenant_invisible(db_session_factory) -> None:
    """对抗①单测版：两租户埋同向量块，各自只见自家 id——WHERE tenant_id 第一防线。"""
    q = "青梧路门店"
    emb = _FixedEmbedder({q: _vec((0, 1.0))})
    a_id = await _add_chunk(
        db_session_factory, tenant_id=TEN_A, seq=0, text_="青梧路 199 号门店指南", embedding=_vec((0, 1.0))
    )
    b_id = await _add_chunk(
        db_session_factory, tenant_id=TEN_B, seq=0, text_="B 租户内部资料", embedding=_vec((0, 1.0)), doc=f"{DOC}-b"
    )
    r = Retriever(db_session_factory, emb)
    assert [h.chunk_id for h in await r.search(TEN_A, q)] == [a_id]
    assert [h.chunk_id for h in await r.search(TEN_B, q)] == [b_id]


async def test_embedding_null_excluded(db_session_factory) -> None:
    """IS NOT NULL 谓词：待回填半成品即使字面全中也不出场（回填完成才可检索）。"""
    q = "退款政策"
    emb = _FixedEmbedder({q: _vec((1, 1.0))})
    ok_id = await _add_chunk(db_session_factory, tenant_id=TEN_A, seq=0, text_="退款需三日", embedding=_vec((1, 1.0)))
    await _add_chunk(db_session_factory, tenant_id=TEN_A, seq=1, text_="退款政策原文全中", embedding=None)
    hits = await Retriever(db_session_factory, emb).search(TEN_A, q)
    assert [h.chunk_id for h in hits] == [ok_id]


async def test_threshold_all_low_returns_empty(db_session_factory) -> None:
    """全低于阈值=检索失败返回空——宁可说不知道（00 M3.5 行）；无语料同归此路。"""
    q = "会员等级"
    emb = _FixedEmbedder({q: _vec((0, 1.0))})
    await _add_chunk(db_session_factory, tenant_id=TEN_A, seq=0, text_="物流时效表", embedding=_vec((1, 1.0)))
    await _add_chunk(db_session_factory, tenant_id=TEN_A, seq=1, text_="发票开具流程", embedding=_vec((2, 1.0)))
    r = Retriever(db_session_factory, emb)
    assert await r.search(TEN_A, q) == []  # 正交 sim=0 且零关键词命中 → score 0 < 0.35
    assert await r.search(TEN_B, q) == []  # 该租户无语料


async def test_top_k_truncation_and_score_order(db_session_factory) -> None:
    """候选池重排后取 top_k 降序出线：4 块只出 2 块，分数严格降。"""
    q = "查询"
    emb = _FixedEmbedder({q: _vec((0, 1.0))})
    ids: list[int] = []
    for i, sim in enumerate((0.9, 0.8, 0.7, 0.6)):
        norm_rest = (1 - sim**2) ** 0.5  # 保单位范数：cos 恰等于 axis0 分量
        ids.append(
            await _add_chunk(
                db_session_factory,
                tenant_id=TEN_A,
                seq=i,
                text_=f"资料{i}",
                embedding=_vec((0, sim), (1 + i, norm_rest)),
            )
        )
    hits = await Retriever(db_session_factory, emb, top_k=2).search(TEN_A, q)
    assert [h.chunk_id for h in hits] == [ids[0], ids[1]]
    assert hits[0].score > hits[1].score
    assert hits[0].similarity == pytest.approx(0.9)


async def test_candidate_pool_lets_rerank_overturn(db_session_factory) -> None:
    """LIMIT=3×top_k 的意义：top_k=1 时字面全中的第二名进池、经重排反超纯向量第一名。"""
    q = "R68 保修"
    emb = _FixedEmbedder({q: _vec((0, 1.0))})
    await _add_chunk(
        db_session_factory,
        tenant_id=TEN_A,
        seq=0,
        text_="型号大全目录",
        embedding=_vec((0, 0.9), (1, (1 - 0.81) ** 0.5)),
    )
    b_id = await _add_chunk(
        db_session_factory, tenant_id=TEN_A, seq=1, text_="R68 保修条款", embedding=_vec((0, 0.8), (2, 0.6))
    )
    hits = await Retriever(db_session_factory, emb, top_k=1).search(TEN_A, q)
    assert [h.chunk_id for h in hits] == [b_id]  # 0.7×0.8+0.3×1.0=0.86 > 0.7×0.9=0.63


async def test_small_tenant_uses_exact_scan(db_conn, db_session_factory) -> None:
    """count ≤ 上限 → SET LOCAL enable_indexscan=off（精确扫描：召回完整性第一开关）。"""
    q = "任意"
    emb = _FixedEmbedder({q: _vec((0, 1.0))})
    await _add_chunk(db_session_factory, tenant_id=TEN_A, seq=0, text_="唯一资料", embedding=_vec((0, 1.0)))
    with _sql_spy(db_conn) as captured:
        await Retriever(db_session_factory, emb).search(TEN_A, q)
    sets = [st for st in captured if "SET LOCAL" in st]
    assert any("enable_indexscan" in st for st in sets)
    assert not any("iterative_scan" in st for st in sets)


async def test_large_tenant_uses_iterative_scan(db_conn, db_session_factory) -> None:
    """count > 上限 → SET LOCAL hnsw.iterative_scan=relaxed_order（第二开关）；
    上限经注入缝压到 0——测试不搬一万行（偏差(31) 参数的存在理由）。"""
    q = "任意"
    emb = _FixedEmbedder({q: _vec((0, 1.0))})
    await _add_chunk(db_session_factory, tenant_id=TEN_A, seq=0, text_="唯一资料", embedding=_vec((0, 1.0)))
    with _sql_spy(db_conn) as captured:
        await Retriever(db_session_factory, emb, exact_scan_max_chunks=0).search(TEN_A, q)
    assert any("hnsw.iterative_scan" in st for st in captured if "SET LOCAL" in st)


async def test_chunk_count_cache_ttl(db_conn, db_session_factory) -> None:
    """计数 60s 缓存：TTL 内新增行不翻转扫描模式（读旧 count），钟推 61s 重查才翻转。"""
    q = "任意"
    emb = _FixedEmbedder({q: _vec((0, 1.0))})
    clock = _FakeClock()
    r = Retriever(db_session_factory, emb, exact_scan_max_chunks=1, clock=clock)
    await _add_chunk(db_session_factory, tenant_id=TEN_A, seq=0, text_="第一块", embedding=_vec((0, 1.0)))
    with _sql_spy(db_conn) as first:
        await r.search(TEN_A, q)  # count=1 ≤ 1 → exact
    await _add_chunk(db_session_factory, tenant_id=TEN_A, seq=1, text_="第二块", embedding=_vec((0, 1.0)))
    with _sql_spy(db_conn) as second:
        await r.search(TEN_A, q)  # TTL 内仍用缓存 count=1 → exact 不翻转
    clock.now += 61.0
    with _sql_spy(db_conn) as third:
        await r.search(TEN_A, q)  # 过期重查 count=2 > 1 → iterative
    assert any("enable_indexscan" in st for st in first)
    assert any("enable_indexscan" in st for st in second)
    assert not any("iterative_scan" in st for st in second)
    assert any("hnsw.iterative_scan" in st for st in third)


async def test_row_mapping_and_meta_roundtrip(db_session_factory) -> None:
    """裸 SQL 列映射契约：chunk_id/document_id/text/meta(jsonb→dict)/similarity/score 全回来。"""
    q = "青梧路"
    emb = _FixedEmbedder({q: _vec((0, 0.6), (1, 0.8))})  # 与块向量夹角 cos=0.6
    cid = await _add_chunk(
        db_session_factory,
        tenant_id=TEN_A,
        seq=0,
        text_="青梧路门店",
        embedding=_vec((0, 1.0)),
        meta={"priority": "high"},
    )
    (hit,) = await Retriever(db_session_factory, emb).search(TEN_A, q)
    assert hit.chunk_id == cid
    assert hit.document_id == DOC
    assert hit.text == "青梧路门店"
    assert hit.meta == {"priority": "high"}
    assert hit.similarity == pytest.approx(0.6)  # float32 噪音由 approx 消化
    assert hit.score == pytest.approx(0.7 * 0.6 + 0.3 * 1.0)  # 覆盖率 {青梧,梧路} 全中=1.0


# ---- 交付③：槽位适配器 RetrievalProvider（#7 接电 + #42 修案 (a)）----


class _BoomEmbedder:
    """恒炸替身：检验 fail-open 边界（异常发自 embed，经 Retriever 裸穿到适配器）。"""

    async def embed(self, texts: Sequence[str], *, tenant_id: str) -> list[list[float]]:
        raise RuntimeError("embedding 通道抖动")


class _NoEventsSink:
    """EventSink 形状哨兵：summarize=None 的 build 路径不许写事件——append 即炸。"""

    session_id = f"ctx-{_SUF}"
    run_id = f"run-{_SUF}"

    async def append(self, event_type, payload):
        raise AssertionError("检索层路径不应写事件")


async def test_provider_wraps_and_adapts_shape(db_session_factory) -> None:
    """形状适配 + 不可信包裹：出线是 ScoredSnippet、text 经 wrap_untrusted(source=retrieval)。"""
    q = "青梧路门店"
    emb = _FixedEmbedder({q: _vec((0, 1.0))})
    await _add_chunk(
        db_session_factory, tenant_id=TEN_A, seq=0, text_="青梧路 199 号门店指南", embedding=_vec((0, 1.0))
    )
    # 协议一致性由这行注解交给 mypy 钉死（Protocol 非 runtime_checkable，静态检查即契约）
    provider: RetrievalProviderLike = RetrievalProvider(Retriever(db_session_factory, emb))
    (snip,) = await provider.search(tenant_id=TEN_A, query=q)
    assert isinstance(snip, ScoredSnippet)
    assert snip.text == wrap_untrusted("青梧路 199 号门店指南", source="retrieval")  # 单一事实源比对，不硬编码格式
    assert snip.score > 0


async def test_provider_fail_open_returns_empty_and_logs(db_session_factory, caplog) -> None:
    """#42 修案 (a)：provider 异常不再裸穿——返空 fail-open + warning 留痕（C34 口径）。"""
    provider = RetrievalProvider(Retriever(db_session_factory, _BoomEmbedder()))
    with caplog.at_level(logging.WARNING):
        out = await provider.search(tenant_id=TEN_A, query="任意")
    assert out == ()
    assert any("fail-open" in r.message for r in caplog.records)


async def test_provider_preserves_order_and_never_trims(db_session_factory) -> None:
    """纯形状适配：保 rerank 序、整条透传不裁剪——预算装填归 builder._pack_snippets（实况块 #4）。"""
    q = "查询"
    emb = _FixedEmbedder({q: _vec((0, 1.0))})
    long_text = "长" * 500  # ~500 token：适配器若自作主张裁剪必现形
    await _add_chunk(
        db_session_factory,
        tenant_id=TEN_A,
        seq=0,
        text_=long_text,
        embedding=_vec((0, 0.9), (1, (1 - 0.81) ** 0.5)),
    )
    await _add_chunk(db_session_factory, tenant_id=TEN_A, seq=1, text_="短资料", embedding=_vec((0, 0.8), (2, 0.6)))
    snips = await RetrievalProvider(Retriever(db_session_factory, emb)).search(tenant_id=TEN_A, query=q)
    assert len(snips) == 2
    assert [s.score for s in snips] == sorted((s.score for s in snips), reverse=True)
    assert long_text in snips[0].text  # 整条在场，只是被包裹


async def test_provider_plugs_into_context_builder(db_session_factory) -> None:
    """#7 接电证明：ContextBuilder 检索槽消费本适配器——检索层消息带标头与包裹入 prompt。"""
    q = "青梧路门店"
    emb = _FixedEmbedder({q: _vec((0, 1.0))})
    await _add_chunk(
        db_session_factory, tenant_id=TEN_A, seq=0, text_="青梧路 199 号门店指南", embedding=_vec((0, 1.0))
    )
    builder = ContextBuilder(
        db_session_factory,
        _NoEventsSink(),
        config=ContextConfig(),
        tenant_id=TEN_A,
        user_id=f"u-{_SUF}",
        retrieval=RetrievalProvider(Retriever(db_session_factory, emb)),
    )
    messages = await builder.build(system_prompt="你是客服助手", user_input=q)
    (layer,) = [m for m in messages if m.content.startswith(_RETRIEVAL_HEADER)]
    assert layer.role == "system"
    assert "source=retrieval]" in layer.content
    assert "青梧路 199 号门店指南" in layer.content


async def test_provider_fail_open_keeps_build_alive(db_session_factory) -> None:
    """#42 回归钉子：检索抖动时 build 照常出 prompt（无检索层、user 原文在场）——run 不死。"""
    builder = ContextBuilder(
        db_session_factory,
        _NoEventsSink(),
        config=ContextConfig(),
        tenant_id=TEN_A,
        user_id=f"u-{_SUF}",
        retrieval=RetrievalProvider(Retriever(db_session_factory, _BoomEmbedder())),
    )
    messages = await builder.build(system_prompt="你是客服助手", user_input="任意问题")
    assert not [m for m in messages if m.content.startswith(_RETRIEVAL_HEADER)]
    assert messages[-1].role == "user"
    assert messages[-1].content == "任意问题"

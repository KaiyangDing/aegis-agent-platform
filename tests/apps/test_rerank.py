"""M3.5 交付①：轻量重排纯函数（零 IO；plans/m3-detailed §4.5）。

覆盖率用例全按"单元集合"心算构造：CJK 连续段取相邻二元组（孤字自成单元）、
非 CJK 取字母数字段小写归一——期望值是精确分数，不赌浮点边界（用 approx 只消
除除法尾差）。
"""

from __future__ import annotations

import pytest
from aegis.apps.support.rag.rerank import RetrievedChunk, keyword_coverage, rerank


def _hit(chunk_id: int, text: str, similarity: float) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=chunk_id, document_id="doc-1", text=text, similarity=similarity)


# ---- keyword_coverage ----


def test_coverage_full_hit_mixed_cjk_english() -> None:
    """CJK/英文混合查询全命中=1.0：单元集 {r68, pro, 退款} 全部在文本里。"""
    assert keyword_coverage("R68 Pro 退款", "R68 Pro 的退款流程如下") == 1.0


def test_coverage_zero_when_nothing_hits() -> None:
    """零命中=0.0：查询单元与文本无交集。"""
    assert keyword_coverage("退款", "物流查询指引") == 0.0


def test_coverage_empty_or_punct_query_is_zero() -> None:
    """空查询/纯标点查询无匹配单元——约定返回 0.0，不抛错（rerank 退化为纯相似度序）。"""
    assert keyword_coverage("", "任意文本") == 0.0
    assert keyword_coverage("，。？！", "任意文本") == 0.0


def test_coverage_monotonic_in_hits() -> None:
    """覆盖率单调：命中单元变多，覆盖率严格上升（同一查询、文本递增命中）。"""
    query = "退款 政策 时限"  # 三个独立 CJK 段 → 单元集 {退款, 政策, 时限}
    low = keyword_coverage(query, "本店退款说明")  # 命中 1/3
    high = keyword_coverage(query, "本店退款政策说明")  # 命中 2/3
    assert low == pytest.approx(1 / 3)
    assert high == pytest.approx(2 / 3)
    assert high > low


def test_coverage_cjk_bigram_granularity() -> None:
    """CJK 连续段按二元组计权："退款政策"→{退款,款政,政策}，只含"退款"的文本=1/3。"""
    assert keyword_coverage("退款政策", "本店退款需三日") == pytest.approx(1 / 3)


def test_coverage_single_cjk_char_query() -> None:
    """孤字 CJK 查询自成单元（否则单字查询永远零单元）。"""
    assert keyword_coverage("退", "退货入口") == 1.0
    assert keyword_coverage("退", "换货入口") == 0.0


def test_coverage_word_units_case_insensitive() -> None:
    """非 CJK 词单元小写归一：PRO 命中 pro。"""
    assert keyword_coverage("PRO", "pro 版本说明") == 1.0


# ---- rerank ----


def test_rerank_score_formula_exact() -> None:
    """score = 0.7×similarity + 0.3×coverage，逐项精确核对。"""
    full, miss = rerank("退款", [_hit(1, "退款说明", 0.5), _hit(2, "物流指引", 0.5)])
    assert full.chunk_id == 1
    assert full.score == pytest.approx(0.7 * 0.5 + 0.3 * 1.0)
    assert miss.score == pytest.approx(0.7 * 0.5 + 0.3 * 0.0)


def test_rerank_literal_match_overtakes_similarity() -> None:
    """字面命中拉回排名：相似度略低但关键词全中的块反超（重排存在的理由）。"""
    out = rerank("R68", [_hit(1, "同族型号大全", 0.6), _hit(2, "R68 参数页", 0.5)])
    assert [h.chunk_id for h in out] == [2, 1]  # 0.65 > 0.42
    assert len(out) == 2  # 重排不截断——top_k 归 Retriever.search（§4.5 第 5 步）


def test_rerank_ties_keep_input_order() -> None:
    """同分保输入序（sorted 稳定）：输入序=SQL 相似度序，确定性与 _pack_snippets 同口径。"""
    out = rerank("无关词", [_hit(1, "甲", 0.4), _hit(2, "乙", 0.4)])
    assert [h.chunk_id for h in out] == [1, 2]


def test_rerank_empty_hits() -> None:
    """空输入空输出：零候选是合法状态（阈值兜底在上游 search 里判）。"""
    assert rerank("退款", []) == []


def test_rerank_returns_new_objects_input_untouched() -> None:
    """rerank 产新对象回填 score，输入的 frozen 实例分毫不动（纯函数契约）。"""
    hits = [_hit(1, "退款说明", 0.5)]
    out = rerank("退款", hits)
    assert hits[0].score == 0.0
    assert out[0] is not hits[0]
    assert out[0].score > 0.0

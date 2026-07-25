"""M3.4 交付③：split_text 纯函数——切块策略的行为面（零 IO，estimate_tokens 做尺）。

用例全用 CJK 串构造：estimate_tokens 对 CJK 恰为 1 token/字（tokens.py:15），
预算断言无 ±1 取整噪音（00 §2.2：测试不赌估算边界）。
"""

from __future__ import annotations

from aegis.apps.support.rag.ingest import split_text
from aegis.core.tokens import estimate_tokens


def _para(n: int, ch: str = "文") -> str:
    return ch * n


def test_empty_text_returns_no_chunks() -> None:
    """空文本/纯空白零块——摄取端上游把关，切块器不造空块。"""
    assert split_text("") == []
    assert split_text("\n\n   \n\n") == []


def test_short_text_single_chunk_verbatim() -> None:
    """预算内单段原样成块：不加不减一个字。"""
    assert split_text("你好世界") == ["你好世界"]


def test_paragraph_aggregation_respects_budget() -> None:
    """段落聚合到预算即封块：绝不在段落中间下刀；每块 token 数 ≤ target。"""
    paras = [_para(100) for _ in range(5)]
    chunks = split_text("\n\n".join(paras), target_tokens=220, overlap_tokens=0)
    assert chunks == [
        "\n\n".join(paras[0:2]),
        "\n\n".join(paras[2:4]),
        paras[4],
    ]
    assert all(estimate_tokens(c) <= 220 for c in chunks)


def test_overlap_seeds_next_chunk_and_zero_disables() -> None:
    """overlap 生效面：前块尾段成为后块开头（对抗"答案跨块边界"）；0=关闭无重叠。"""
    paras = [_para(100, "甲"), _para(100, "乙"), _para(100, "丙")]
    text = "\n\n".join(paras)
    with_overlap = split_text(text, target_tokens=220, overlap_tokens=100)
    assert with_overlap[0] == "\n\n".join(paras[0:2])
    assert with_overlap[1].startswith(paras[1])  # 尾段"乙"被携带为下块种子
    assert paras[2] in with_overlap[1]
    without = split_text(text, target_tokens=220, overlap_tokens=0)
    assert without[1] == paras[2]  # 关闭后下块只有新内容


def test_long_paragraph_split_by_sentences() -> None:
    """单段超预算：句界再切（语义完整性退一级承诺到句子），每块 ≤ target。"""
    sentence = _para(100, "句") + "。"
    chunks = split_text(sentence * 3, target_tokens=150)
    assert len(chunks) == 3
    assert all(c.endswith("。") for c in chunks)
    assert all(estimate_tokens(c) <= 150 for c in chunks)


def test_hard_split_when_no_sentence_boundary() -> None:
    """最后手段：无句界超长串按估算窗硬切——内容一字不丢，每块 ≤ target。"""
    blob = _para(500)
    chunks = split_text(blob, target_tokens=200)
    assert "".join(chunks) == blob
    assert len(chunks) == 3
    assert all(estimate_tokens(c) <= 200 for c in chunks)


def test_overlap_seed_never_busts_budget() -> None:
    """回归钉子（③校验揪出）：封块后"种子+新段"超预算必须丢种子——绝不产出超预算块。
    反例形状：小段(30)+大段(380)，overlap 允许小段做种子、但种子+大段=410 > 400。"""
    text = "\n\n".join([_para(30, "小"), _para(380, "大")])
    chunks = split_text(text, target_tokens=400, overlap_tokens=50)
    assert chunks == [_para(30, "小"), _para(380, "大")]  # 种子被丢：第二块不携带"小"
    assert all(estimate_tokens(c) <= 400 for c in chunks)

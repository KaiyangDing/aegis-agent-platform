from aegis.core.tokens import estimate_tokens


def test_empty_is_zero():
    assert estimate_tokens("") == 0


def test_cjk_counts_per_char():
    assert estimate_tokens("退款申请") == 4


def test_ascii_four_chars_per_token():
    assert estimate_tokens("abcdefgh") == 2


def test_mixed_text():
    assert estimate_tokens("退款refund") == 4  # 2 CJK + ceil(6/4)=2


def test_cjk_range_single_source_across_consumers():
    """M4.7 ⑳：CJK 区间单点——估算器与重排分词消费同一常量；区间外邻字符
    （U+3400 扩展A 首字）两个消费方都不认，改区间必须两边同时变。"""
    from aegis.apps.support.rag.rerank import _CJK_RE
    from aegis.core.tokens import CJK_FIRST, CJK_LAST

    assert estimate_tokens(CJK_FIRST) == 1
    assert estimate_tokens(CJK_LAST) == 1
    assert _CJK_RE.fullmatch(CJK_FIRST + CJK_LAST) is not None
    assert _CJK_RE.search("\u3400") is None

from aegis.core.tokens import estimate_tokens


def test_empty_is_zero():
    assert estimate_tokens("") == 0


def test_cjk_counts_per_char():
    assert estimate_tokens("退款申请") == 4


def test_ascii_four_chars_per_token():
    assert estimate_tokens("abcdefgh") == 2


def test_mixed_text():
    assert estimate_tokens("退款refund") == 4  # 2 CJK + ceil(6/4)=2

"""base.py 纯函数的直接单测（适配器测试覆盖的是它们经 HTTP 的行为，这里钉语义本身）。"""

from aegis.gateway.providers.base import parse_retry_after, sanitize_error_text


def test_sanitize_masks_api_keys():
    dirty = "Incorrect API key provided: sk-abc123DEF456ghi789 (request id: xyz)"
    clean = sanitize_error_text(dirty)
    assert "sk-abc123DEF456ghi789" not in clean
    assert "sk-***" in clean


def test_sanitize_truncates_to_limit():
    assert len(sanitize_error_text("x" * 10_000)) <= 200
    assert len(sanitize_error_text("x" * 10_000, limit=120)) <= 120


def test_sanitize_leaves_normal_text_alone():
    msg = "model not found: qwen-flash-9000"
    assert sanitize_error_text(msg) == msg  # 打码只认 key 模式，不误伤正常错误信息


def test_parse_retry_after_seconds():
    assert parse_retry_after("3") == 3.0
    assert parse_retry_after("2.5") == 2.5


def test_parse_retry_after_http_date_past_clamps_to_zero():
    # 过去的日期换算出负数 → 钳位为 0（立即可重试），绝不返回负退避
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0


def test_parse_retry_after_garbage_is_none():
    assert parse_retry_after("soon-ish") is None
    assert parse_retry_after("") is None
    assert parse_retry_after(None) is None

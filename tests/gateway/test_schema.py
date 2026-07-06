import pytest
from pydantic import ValidationError

from aegis.gateway.schema import (
    LLMRequest,
    Message,
    TextDelta,
    ToolCall,
    chunk_adapter,
)


def _msg() -> list[Message]:
    return [Message(role="user", content="你好")]


def test_request_requires_at_least_one_message():
    with pytest.raises(ValidationError):
        LLMRequest(tier="fast", messages=[], tenant_id="t1")


def test_tier_is_validated():
    with pytest.raises(ValidationError):
        LLMRequest(tier="超强档", messages=_msg(), tenant_id="t1")  # type: ignore[arg-type]


def test_tool_arguments_stay_raw():
    # 模型吐了坏 JSON —— 传输层照单全收，处理它是 L2 的事（分层）
    tc = ToolCall(id="c1", name="refund_apply", arguments_json='{"amount": 不合法')
    assert tc.arguments_json == '{"amount": 不合法'


def test_chunk_dict_restores_to_correct_subtype():
    chunk = chunk_adapter.validate_python({"type": "text_delta", "text": "你"})
    assert isinstance(chunk, TextDelta)


def test_chunk_json_roundtrip_lossless():
    # M2 录制回放（cassette）的地基：chunk 必须无损 JSON 往返
    chunk = TextDelta(text="半句话")
    restored = chunk_adapter.validate_json(chunk_adapter.dump_json(chunk))
    assert restored == chunk


def test_unknown_chunk_type_rejected():
    with pytest.raises(ValidationError):
        chunk_adapter.validate_python({"type": "video_delta", "data": "x"})


def test_request_ids_are_unique():
    r1 = LLMRequest(tier="fast", messages=_msg(), tenant_id="t1")
    r2 = LLMRequest(tier="fast", messages=_msg(), tenant_id="t1")
    assert r1.request_id != r2.request_id


# ---------- 审计加固 B：tenant_id 是要拼进 Redis key 的内部标识符 ----------


def test_tenant_id_rejects_empty_and_key_breaking_chars():
    for bad in ["", "tA:evil", "tA*", "租户甲", "a" * 65]:
        with pytest.raises(ValidationError):
            LLMRequest(tier="fast", messages=_msg(), tenant_id=bad)


def test_tenant_id_accepts_normal_identifiers():
    for ok in ["t1", "tenant-a", "TENANT_B", "a" * 64]:
        assert LLMRequest(tier="fast", messages=_msg(), tenant_id=ok).tenant_id == ok

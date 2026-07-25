"""M3.6 交付①：意图路由——fast 档单次分类（不是 Agent）+ FAQ 直答。

覆盖三面：词表映射与宽容解析（plans §4.6 陷阱 1）、fail-open 与绝不重试
（C34/D8、ADR-002 红线）、两函数请求形状（fast 档/零工具/身份透传）。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from aegis.apps.support.intent import INTENT_PROMPT, Intent, answer_faq, classify
from aegis.gateway.errors import GatewayExhausted
from aegis.gateway.schema import LLMChunk, LLMRequest, StopChunk, TextDelta, UsageChunk


class _ScriptedGateway:
    """最小假网关：预置 chunk 剧本，complete 调用即回放并记录请求（GatewayLike 形状）。"""

    def __init__(self, chunks: list[LLMChunk]) -> None:
        self._chunks = chunks
        self.requests: list[LLMRequest] = []

    def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        self.requests.append(req)
        chunks = self._chunks

        async def _stream() -> AsyncGenerator[LLMChunk]:
            for c in chunks:
                yield c

        return _stream()


def _text_gateway(*parts: str) -> _ScriptedGateway:
    """便捷构造：纯文本分片 + end_turn 收尾。"""
    chunks: list[LLMChunk] = [TextDelta(text=p) for p in parts]
    chunks.append(StopChunk(reason="end_turn"))
    return _ScriptedGateway(chunks)


class _RaisingGateway:
    """首块前爆炸的假网关：异常从流内抛出（真实网关的异常面），并计数调用次数。"""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.calls = 0

    def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        self.calls += 1
        exc = self._exc

        async def _stream() -> AsyncGenerator[LLMChunk]:
            raise exc
            yield TextDelta(text="")  # pragma: no cover——仅为让函数成为生成器

        return _stream()


# ---- classify：词表映射与宽容解析 ----


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("faq", Intent.FAQ),
        ("rag", Intent.RAG),
        ("tool", Intent.TOOL),
        ("handoff", Intent.HANDOFF),
    ],
)
async def test_classify_four_words(answer: str, expected: Intent) -> None:
    """四词各归其类：模型按 prompt 词表输出时逐词映射。"""
    got = await classify(_text_gateway(answer), "随便一句话", tenant_id="tenant-a", session_id="s-1")
    assert got is expected


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (" FAQ \n", Intent.FAQ),  # 大小写与空白
        ("faq。", Intent.FAQ),  # 尾随标点
        ("分类：rag", Intent.RAG),  # 前缀加料（plans §4.6 陷阱 1 原型）
    ],
)
async def test_classify_rescues_decorated_output(answer: str, expected: Intent) -> None:
    """加料输出救回：精确不中时，恰含词表一词的子串匹配仍归位。"""
    got = await classify(_text_gateway(answer), "随便一句话", tenant_id="tenant-a", session_id="s-1")
    assert got is expected


async def test_classify_ambiguous_output_goes_agent() -> None:
    """歧义输出（含两个词表词）→ AGENT：宽容解析绝不把歧义洗成裁决。"""
    got = await classify(_text_gateway("faq或rag"), "退货政策？", tenant_id="tenant-a", session_id="s-1")
    assert got is Intent.AGENT


async def test_classify_hallucination_goes_agent() -> None:
    """词表外自由发挥 → AGENT（D8）：不重试、不追问，直走主 Agent 标准档。"""
    got = await classify(_text_gateway("这个问题比较复杂"), "你好", tenant_id="tenant-a", session_id="s-1")
    assert got is Intent.AGENT


async def test_classify_multichunk_stream_is_joined() -> None:
    """分片流拼接后再解析：'fa'+'q' 两块也归 FAQ（流式消费不是逐块判词）。"""
    got = await classify(_text_gateway("fa", "q"), "你好", tenant_id="tenant-a", session_id="s-1")
    assert got is Intent.FAQ


# ---- classify：fail-open 与绝不重试 ----


async def test_classify_gateway_error_goes_agent_and_never_retries() -> None:
    """网关异常 → AGENT（C34 fail-open）且恰调一次：绝不重试是 ADR-002 红线。"""
    gw = _RaisingGateway(GatewayExhausted("全部候选耗尽"))
    got = await classify(gw, "你好", tenant_id="tenant-a", session_id="s-1")
    assert got is Intent.AGENT
    assert gw.calls == 1


# ---- classify：请求形状 ----


async def test_classify_request_shape() -> None:
    """形状钉死：fast 档、零工具、system=INTENT_PROMPT、身份透传、deadline 缺省 10s。"""
    gw = _text_gateway("faq")
    await classify(gw, "营业时间？", tenant_id="tenant-a", session_id="s-9")
    req = gw.requests[0]
    assert req.tier == "fast"
    assert req.tools == []
    assert [m.role for m in req.messages] == ["system", "user"]
    assert req.messages[0].content == INTENT_PROMPT
    assert req.messages[1].content == "营业时间？"
    assert req.tenant_id == "tenant-a"
    assert req.session_id == "s-9"
    assert req.deadline_s == 10.0


# ---- answer_faq ----


async def test_answer_faq_streams_text_only() -> None:
    """流式产出只含 TextDelta 文本：usage/stop 等非文本块被过滤。"""
    chunks: list[LLMChunk] = [
        TextDelta(text="营业时间"),
        UsageChunk(model="m", prompt_tokens=1, completion_tokens=1),
        TextDelta(text="是 9:00–18:00。"),
        StopChunk(reason="end_turn"),
    ]
    gw = _ScriptedGateway(chunks)
    stream = answer_faq(gw, "几点营业？", tenant_id="tenant-a", session_id="s-1", faq_digest="FAQ 摘要")
    parts = [p async for p in stream]
    assert parts == ["营业时间", "是 9:00–18:00。"]


async def test_answer_faq_request_shape() -> None:
    """形状钉死：system=faq_digest 原文（prompt 政策归租户配置，机制不定政策）。"""
    gw = _text_gateway("好的")
    stream = answer_faq(gw, "几点营业？", tenant_id="tenant-b", session_id="s-2", faq_digest="digest 原文")
    _ = [p async for p in stream]
    req = gw.requests[0]
    assert req.tier == "fast"
    assert req.tools == []
    assert [m.role for m in req.messages] == ["system", "user"]
    assert req.messages[0].content == "digest 原文"
    assert req.messages[1].content == "几点营业？"
    assert req.tenant_id == "tenant-b"
    assert req.session_id == "s-2"
    assert req.deadline_s == 10.0


async def test_answer_faq_propagates_gateway_error() -> None:
    """直答是主路径不是增强层：异常裸传播，处置权归调用方（M3.8/M3.10 接线）。"""
    gw = _RaisingGateway(GatewayExhausted("耗尽"))
    with pytest.raises(GatewayExhausted):
        _ = [p async for p in answer_faq(gw, "你好", tenant_id="tenant-a", session_id="s-1", faq_digest="d")]

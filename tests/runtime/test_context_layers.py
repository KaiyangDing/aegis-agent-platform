"""M2.5 交付①：ContextBuilder 注入面与四个简单层——预算即策略（plans/m2.5 §4.2、§5.1）。

历史层（摘要+旧轮）交付②接入；本文件的用例不触 DB、不写事件——
_Sink.append 被调用即失败，钉死"层编译不产生副作用"。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from aegis.core.tokens import estimate_tokens
from aegis.gateway.schema import Message, ToolCall
from aegis.runtime.context import (
    _FOLDED_TOOL_TEMPLATE,
    _MEMORY_HEADER,
    _RETRIEVAL_HEADER,
    ContextBuilder,
    MemoryProviderLike,
    RetrievalProviderLike,
    ScoredSnippet,
    _message_tokens,
)
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.spec import ContextConfig


class _Sink:
    """假事件槽：满足 EventSink 形状；交付①的层编译不该写任何事件。"""

    @property
    def session_id(self) -> str:
        return "s-ctx"

    @property
    def run_id(self) -> str:
        return "r-ctx"

    async def append(self, event_type: EventType, payload: Mapping[str, Any]) -> AgentEvent:
        raise AssertionError("层编译不应写事件")


class _Memory:
    """返回固定 snippets 的记忆假件（零真实调用，00 §6.0）。"""

    def __init__(self, snippets: Sequence[ScoredSnippet]) -> None:
        self._snippets = snippets

    async def fetch(self, *, tenant_id: str, user_id: str, query: str) -> Sequence[ScoredSnippet]:
        return self._snippets


class _Retrieval:
    """返回固定 snippets 的检索假件。"""

    def __init__(self, snippets: Sequence[ScoredSnippet]) -> None:
        self._snippets = snippets

    async def search(self, *, tenant_id: str, query: str) -> Sequence[ScoredSnippet]:
        return self._snippets


class _Bomb:
    """被调用即炸的 provider：证明关层 = 真不调用（D14/I3）。"""

    async def fetch(self, *, tenant_id: str, user_id: str, query: str) -> Sequence[ScoredSnippet]:
        raise AssertionError("memory_budget=0 不应调用 provider")

    async def search(self, *, tenant_id: str, query: str) -> Sequence[ScoredSnippet]:
        raise AssertionError("retrieval_budget=0 不应调用 provider")


# mypy 静态证明：假件满足两 Protocol 形状（§6 验收"形状可实现"）
_PROTO_CHECK_MEMORY: MemoryProviderLike = _Memory([])
_PROTO_CHECK_RETRIEVAL: RetrievalProviderLike = _Retrieval([])


def _builder(factory: Any, **kw: Any) -> ContextBuilder:
    """默认 config/tenant/user 的构造工厂（factory 交付①不被触碰，交付②读投影）。"""
    kw.setdefault("config", ContextConfig())
    return ContextBuilder(factory, _Sink(), tenant_id="t-ctx", user_id="u-ctx", **kw)


def _tool_round(*results: tuple[str, str]) -> list[Message]:
    """构造一节工具轮：assistant(tool_calls) + 各 tool 结果消息（(tool_call_id, content) 对）。"""
    calls = [ToolCall(id=cid, name="demo_tool", arguments_json="{}") for cid, _ in results]
    msgs = [Message(role="assistant", content="", tool_calls=calls)]
    msgs += [Message(role="tool", content=text, tool_call_id=cid) for cid, text in results]
    return msgs


async def test_layer_order_snapshot(db_session_factory) -> None:
    """D12 次序快照：system → 记忆 → 检索 → user → working（历史层交付②插入）；无产物层不占位。"""
    b = _builder(
        db_session_factory,
        memory=_Memory([ScoredSnippet(text="老客户", score=0.9)]),
        retrieval=_Retrieval([ScoredSnippet(text="退货政策", score=0.5)]),
    )
    out = await b.build(system_prompt="规则", user_input="问题", working=_tool_round(("tc-1", "结果")))
    assert [m.role for m in out] == ["system", "system", "system", "user", "assistant", "tool"]
    assert out[1].content.startswith(_MEMORY_HEADER)
    assert out[2].content.startswith(_RETRIEVAL_HEADER)
    empty = _builder(db_session_factory, memory=_Memory([]), retrieval=_Retrieval([]))
    out2 = await empty.build(system_prompt="规则", user_input="问题")
    assert [m.role for m in out2] == ["system", "user"]


async def test_system_layer_verbatim(db_session_factory) -> None:
    """system 原文一字不改进首条消息（固定层，03 §3）。"""
    b = _builder(db_session_factory)
    prompt = "你是云杉电商的客服助手。\n规则：不许编造。"
    out = await b.build(system_prompt=prompt, user_input="你好")
    assert out[0].role == "system"
    assert out[0].content == prompt


async def test_system_over_budget_is_loud(db_session_factory) -> None:
    """超 system_budget ⇒ ValueError（D15 fail-loud：固定层没有合法降级，那是 L3 配置 bug）。"""
    b = _builder(db_session_factory, config=ContextConfig(system_budget=10))
    with pytest.raises(ValueError, match="system_budget"):
        await b.build(system_prompt="长" * 11, user_input="你好")


async def test_memory_none_yields_no_layer(db_session_factory) -> None:
    """memory=None（M2 常态，槽位实装归 M3.5）⇒ 无记忆层消息。"""
    b = _builder(db_session_factory)
    out = await b.build(system_prompt="规则", user_input="问题")
    assert not any(m.content.startswith(_MEMORY_HEADER) for m in out)


async def test_retrieval_none_yields_no_layer(db_session_factory) -> None:
    """retrieval=None ⇒ 无检索层消息。"""
    b = _builder(db_session_factory)
    out = await b.build(system_prompt="规则", user_input="问题")
    assert not any(m.content.startswith(_RETRIEVAL_HEADER) for m in out)


async def test_zero_budget_skips_provider_call(db_session_factory) -> None:
    """预算 0 = 显式关层且 provider 零调用——不调用才是真关闭，省一次 RPC/向量检索（D14/I3）。"""
    bomb = _Bomb()
    b = _builder(
        db_session_factory,
        config=ContextConfig(memory_budget=0, retrieval_budget=0),
        memory=bomb,
        retrieval=bomb,
    )
    out = await b.build(system_prompt="规则", user_input="问题")
    assert [m.role for m in out] == ["system", "user"]


async def test_memory_truncates_low_scores(db_session_factory) -> None:
    """D13：乱序 score 输入 ⇒ 按降序整条装入、低分被截、装不下即停；标头 token 计入层预算。"""
    header_cost = estimate_tokens(_MEMORY_HEADER)
    b = _builder(
        db_session_factory,
        config=ContextConfig(memory_budget=header_cost + 10),
        memory=_Memory(
            [
                ScoredSnippet(text="低" * 6, score=0.2),
                ScoredSnippet(text="高" * 6, score=0.9),
                ScoredSnippet(text="中" * 6, score=0.5),
            ]
        ),
    )
    out = await b.build(system_prompt="规则", user_input="问题")
    mem = next(m for m in out if m.content.startswith(_MEMORY_HEADER))
    # 可用 10 token：最高分"高"×6 装入后，"中"×6 装不下即停——"低"更轮不到
    assert mem.content == _MEMORY_HEADER + "高" * 6


async def test_retrieval_keeps_provider_order(db_session_factory) -> None:
    """检索层按 provider 返回序装入（已重排，builder 不再排序）；产物换行拼接。"""
    b = _builder(
        db_session_factory,
        retrieval=_Retrieval([ScoredSnippet(text="第一条", score=0.1), ScoredSnippet(text="第二条", score=0.9)]),
    )
    out = await b.build(system_prompt="规则", user_input="问题")
    ret = next(m for m in out if m.content.startswith(_RETRIEVAL_HEADER))
    assert ret.content == _RETRIEVAL_HEADER + "第一条\n第二条"


async def test_layer_headers_present(db_session_factory) -> None:
    """记忆/检索消息各带标头（层间分隔符；"不可信"措辞归 M2.8 wrap_untrusted，不在此断言）。"""
    b = _builder(
        db_session_factory,
        memory=_Memory([ScoredSnippet(text="画像", score=1.0)]),
        retrieval=_Retrieval([ScoredSnippet(text="知识", score=1.0)]),
    )
    out = await b.build(system_prompt="规则", user_input="问题")
    assert sum(1 for m in out if m.content.startswith(_MEMORY_HEADER)) == 1
    assert sum(1 for m in out if m.content.startswith(_RETRIEVAL_HEADER)) == 1
    assert all(m.role == "system" for m in out if m.content.startswith((_MEMORY_HEADER, _RETRIEVAL_HEADER)))


async def test_user_input_is_last_before_working(db_session_factory) -> None:
    """I1：user_input 恒在 working 之前的最后一位；无 working 时是末条。"""
    b = _builder(db_session_factory)
    working = _tool_round(("tc-1", "结果"))
    out = await b.build(system_prompt="规则", user_input="当前问题", working=working)
    assert out[-len(working) - 1].role == "user"
    assert out[-len(working) - 1].content == "当前问题"
    out2 = await b.build(system_prompt="规则", user_input="当前问题")
    assert out2[-1].role == "user"
    assert out2[-1].content == "当前问题"


async def test_working_within_budget_untouched(db_session_factory) -> None:
    """预算内 working 逐字节原样透传（I4 的对照面）。"""
    b = _builder(db_session_factory)
    working = _tool_round(("tc-1", "已发货"), ("tc-2", "明天到"))
    out = await b.build(system_prompt="规则", user_input="问题", working=working)
    assert out[-len(working) :] == working


async def test_working_folds_oldest_tool_message_first(db_session_factory) -> None:
    """D6：层聚合超预算 ⇒ 最老 tool 消息整条替换为折叠标注（含 tool_call_id 可回溯）；较新的保留。"""
    b = _builder(db_session_factory, config=ContextConfig(tool_results_budget=60))
    working = _tool_round(("tc-old", "旧" * 100), ("tc-new", "新" * 10))
    out = await b.build(system_prompt="规则", user_input="问题", working=working)
    old_msg = next(m for m in out if m.role == "tool" and m.tool_call_id == "tc-old")
    new_msg = next(m for m in out if m.role == "tool" and m.tool_call_id == "tc-new")
    assert old_msg.content == _FOLDED_TOOL_TEMPLATE.format(tool_call_id="tc-old")
    assert new_msg.content == "新" * 10


async def test_fold_never_touches_assistant_tool_calls(db_session_factory) -> None:
    """I4：折叠只动 role="tool" 的 content——assistant 的 arguments_json 是协议字段，字节不变。"""
    big_args = '{"ids": "' + "x" * 400 + '"}'
    call = ToolCall(id="tc-1", name="demo_tool", arguments_json=big_args)
    working = [
        Message(role="assistant", content="", tool_calls=[call]),
        Message(role="tool", content="旧" * 50, tool_call_id="tc-1"),
    ]
    b = _builder(db_session_factory, config=ContextConfig(tool_results_budget=5))
    out = await b.build(system_prompt="规则", user_input="问题", working=working)
    assert out[-2] == working[0]
    assert out[-1].content == _FOLDED_TOOL_TEMPLATE.format(tool_call_id="tc-1")


async def test_input_total_invariant(db_session_factory) -> None:
    """交付③预铺：各层打满时输出总 token ≤ input_total（标注开销由 ±15% 余量消化，C25）。"""
    cfg = ContextConfig()
    b = _builder(
        db_session_factory,
        config=cfg,
        memory=_Memory([ScoredSnippet(text="忆" * 100, score=1.0 - i / 100) for i in range(50)]),
        retrieval=_Retrieval([ScoredSnippet(text="识" * 100, score=0.5) for _ in range(50)]),
    )
    working = _tool_round(*[(f"tc-{i}", "果" * 900) for i in range(5)])
    out = await b.build(system_prompt="规" * 100, user_input="问" * 100, working=working)
    assert sum(_message_tokens(m) for m in out) <= cfg.input_total


async def test_build_is_deterministic(db_session_factory) -> None:
    """I2：同输入双跑逐字节相同——M2.6 cassette 匹配与 M2.12"逐事件一致"的前提。"""

    def make() -> ContextBuilder:
        return _builder(
            db_session_factory,
            memory=_Memory([ScoredSnippet(text="画像" * 30, score=0.7), ScoredSnippet(text="工单" * 30, score=0.9)]),
            retrieval=_Retrieval([ScoredSnippet(text="政策" * 40, score=0.3)]),
        )

    working = _tool_round(("tc-1", "结" * 50))
    a = await make().build(system_prompt="规则", user_input="问题", working=working)
    b = await make().build(system_prompt="规则", user_input="问题", working=working)
    assert a == b

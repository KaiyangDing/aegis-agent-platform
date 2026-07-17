"""M2.1 交付①：spec.py 的口径测试。

钉死三件事：枚举值稳定（事件 payload / 回放兼容）、"六道闸门"术语口径、
策略与预算类型的冻结语义与防呆。
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace

import pytest

from aegis.runtime.spec import (
    TERMINATION_GATES,
    AgentSpec,
    ContextConfig,
    LoopPolicy,
    SubAgentPolicy,
    TerminationReason,
)
from aegis.runtime.tools import SideEffect, ToolDef


def test_termination_reason_values_are_stable() -> None:
    """值快照：改任何一个值 = 破坏历史事件重放，本测试必须先红。"""
    assert {r.value for r in TerminationReason} == {
        "completed",
        "max_iterations",
        "step_timeout",
        "token_budget_exceeded",
        "repeated_calls",
        "protocol_violation",
        "cancelled",
        "gateway_rejected",
    }


def test_termination_reason_serializes_as_plain_string() -> None:
    """StrEnum：str() 与 json 序列化直接得到裸字符串，可径直进 payload。"""
    assert str(TerminationReason.GATEWAY_REJECTED) == "gateway_rejected"
    assert json.dumps(TerminationReason.COMPLETED) == '"completed"'


def test_termination_gates_are_exactly_six() -> None:
    """00 §2.2 术语口径：六道闸门 = 7 类 - 正常完成；gateway_rejected 不算闸门。"""
    assert len(TERMINATION_GATES) == 6
    assert TerminationReason.COMPLETED not in TERMINATION_GATES
    assert TerminationReason.GATEWAY_REJECTED not in TERMINATION_GATES


def test_loop_policy_defaults_match_design_doc() -> None:
    """03 §2 表的默认阈值列（approval_ttl_s 随 M2.9 P1 拍板方案 A 加入，默认 1 小时）。"""
    p = LoopPolicy()
    assert p.max_iterations == 10
    assert p.llm_step_timeout_s == 90.0
    assert p.tool_step_timeout_s == 30.0
    assert p.session_token_budget == 50_000
    assert p.repeat_call_limit == 3
    assert p.protocol_retry_limit == 2
    assert p.approval_ttl_s == 3600.0


def test_loop_policy_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        LoopPolicy().max_iterations = 99  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("max_iterations", 0),
        ("llm_step_timeout_s", 0.0),
        ("tool_step_timeout_s", -1.0),
        ("session_token_budget", 0),
        ("repeat_call_limit", 0),
        ("protocol_retry_limit", -1),
        ("approval_ttl_s", 0.0),
    ],
)
def test_loop_policy_rejects_invalid(field: str, bad: float) -> None:
    with pytest.raises(ValueError, match=field):
        replace(LoopPolicy(), **{field: bad})  # type: ignore[arg-type]


def test_context_config_defaults_match_design_doc() -> None:
    """03 §3 表的六层默认预算。"""
    c = ContextConfig()
    assert c.system_budget == 1_500
    assert c.memory_budget == 1_000
    assert c.history_budget == 4_000
    assert c.retrieval_budget == 3_000
    assert c.tool_results_budget == 3_000
    assert c.output_reserve == 4_000


def test_context_config_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        ContextConfig().output_reserve = 0  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("system_budget", 0),
        ("output_reserve", 0),
        ("memory_budget", -1),
        ("history_budget", -1),
        ("retrieval_budget", -1),
        ("tool_results_budget", -1),
    ],
)
def test_context_config_rejects_invalid(field: str, bad: int) -> None:
    with pytest.raises(ValueError, match=field):
        replace(ContextConfig(), **{field: bad})


def test_context_config_allows_zero_optional_layers() -> None:
    """中间四层可显式关闭（=0）——例如无工具、无 RAG 的纯对话 Agent。"""
    c = ContextConfig(memory_budget=0, history_budget=0, retrieval_budget=0, tool_results_budget=0)
    assert c.input_total == c.system_budget


def test_context_config_input_total() -> None:
    assert ContextConfig().input_total == 12_500


def test_sub_agent_policy_is_v1_locked() -> None:
    """ADR-002：v1 恒 DISABLED。v2 想加成员，先让这条红、重新过 ADR。"""
    assert [p.value for p in SubAgentPolicy] == ["disabled"]


def test_agent_spec_defaults() -> None:
    spec = AgentSpec(system_prompt="你是云杉电商的客服助手。")
    assert spec.tools == ()
    assert spec.policy == LoopPolicy()
    assert spec.context_config == ContextConfig()
    assert spec.model_tier == "standard"
    assert spec.sub_agent_policy is SubAgentPolicy.DISABLED
    assert dict(spec.tenant_config) == {}


def test_agent_spec_is_frozen() -> None:
    spec = AgentSpec(system_prompt="x")
    with pytest.raises(FrozenInstanceError):
        spec.model_tier = "fast"  # type: ignore[misc]


def test_agent_spec_rejects_blank_prompt() -> None:
    with pytest.raises(ValueError, match="system_prompt"):
        AgentSpec(system_prompt="   ")


def test_agent_spec_rejects_unknown_tier() -> None:
    """Literal 只防静态；L3 从租户配置读出的裸字符串靠这道运行时防线。"""
    with pytest.raises(ValueError, match="model_tier"):
        AgentSpec(system_prompt="x", model_tier="turbo")  # type: ignore[arg-type]


def test_agent_spec_rejects_duplicate_tool_names() -> None:
    async def _h() -> None: ...

    dup = ToolDef(name="dup", description="占位", handler=_h, side_effect=SideEffect.READ)
    with pytest.raises(ValueError, match="dup"):
        AgentSpec(system_prompt="x", tools=(dup, dup))

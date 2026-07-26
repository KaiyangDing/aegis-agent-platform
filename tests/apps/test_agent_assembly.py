"""M3.8 交付①：装配器——工具白名单/预算与 TTL 注入/9 字段注入面/模板预算。

纯构造测试零 DB：TenantRecord 直接实例化（ORM 类不挂会话即普通对象）。
"""

from __future__ import annotations

from typing import Any

import pytest

from aegis.apps.support.agent import ALL_TOOLS, build_agent_spec
from aegis.core.tenancy import TenantRecord
from aegis.core.tokens import estimate_tokens
from aegis.runtime.spec import ContextConfig, LoopPolicy

_A_TOOLS = ["order_query", "logistics_query", "refund_apply", "ticket_create"]


def _tenant(config: dict[str, Any] | None = None, *, name: str = "云杉数码商城") -> TenantRecord:
    return TenantRecord(id="t-asm", name=name, config=config or {}, token_budget_monthly=0)


def test_all_tools_ledger() -> None:
    """五工具清单：name→ToolDef 映射自洽——白名单点名的事实源。"""
    assert set(ALL_TOOLS) == {"order_query", "logistics_query", "ticket_create", "refund_apply", "coupon_grant"}
    assert all(ALL_TOOLS[n].name == n for n in ALL_TOOLS)


def test_tenant_a_toolset_order_stable() -> None:
    """白名单按 config 点名且保序（specs 顺序进 LLMRequest=回放确定性一环）。"""
    spec = build_agent_spec(_tenant({"tools": _A_TOOLS, "approval_threshold": 200}))
    assert [t.name for t in spec.tools] == _A_TOOLS


def test_tenant_b_toolset_exactly_two() -> None:
    """工具面=攻击面：B 只装订单+优惠券，一个不多（§4.8 陷阱 2："反正闸门会拦"是错的）。"""
    spec = build_agent_spec(_tenant({"tools": ["order_query", "coupon_grant"]}, name="云杉生鲜超市"))
    assert [t.name for t in spec.tools] == ["order_query", "coupon_grant"]


def test_unknown_tool_name_raises() -> None:
    """未知工具名=配置错误：启动时炸，不在凌晨的流量里炸（parse_routes 同哲学）。"""
    with pytest.raises(ValueError, match="未知工具"):
        build_agent_spec(_tenant({"tools": ["order_query", "no_such_tool"]}))


def test_duplicate_tool_names_deduped() -> None:
    """config 重复引入去重保序（§4.8 陷阱 1：AgentSpec 构造期重名防呆是帮手，装配器用 dict 语义先消化）。"""
    spec = build_agent_spec(_tenant({"tools": ["order_query", "order_query", "coupon_grant"]}))
    assert [t.name for t in spec.tools] == ["order_query", "coupon_grant"]


def test_budget_and_approval_ttl_injected() -> None:
    """session_token_budget 与 approval_ttl_s 从租户 config 注入（实况块 #8）；其余阈值走默认。"""
    spec = build_agent_spec(_tenant({"tools": [], "session_token_budget": 120_000, "approval_ttl_s": 7200}))
    assert spec.policy.session_token_budget == 120_000
    assert spec.policy.approval_ttl_s == 7200.0
    assert spec.policy.tool_step_timeout_s == LoopPolicy().tool_step_timeout_s


def test_budget_defaults_when_config_silent() -> None:
    spec = build_agent_spec(_tenant({"tools": []}))
    assert spec.policy.session_token_budget == LoopPolicy().session_token_budget
    assert spec.policy.approval_ttl_s == LoopPolicy().approval_ttl_s


def test_memory_off_retrieval_default() -> None:
    """P1 砍长期记忆：memory_budget=0 显式关层（不调 provider 才是真关闭 D14）；检索层预算保默认。"""
    spec = build_agent_spec(_tenant({"tools": []}))
    assert spec.context_config.memory_budget == 0
    assert spec.context_config.retrieval_budget == ContextConfig().retrieval_budget


def test_tenant_config_passthrough_opaque() -> None:
    """tenant_config 原样透传（运行时不解释，解释权在 risk_policy 等 L3 注入点）。"""
    spec = build_agent_spec(_tenant({"tools": [], "approval_threshold": 200, "coupon_threshold": 30}))
    assert spec.tenant_config["approval_threshold"] == 200
    assert spec.tenant_config["coupon_threshold"] == 30


def test_system_prompt_has_tenant_name_and_fits_budget() -> None:
    """模板注入租户名；估算 token 不超 system_budget——D15 fail-loud 的防线在装配期先量一次。"""
    spec = build_agent_spec(_tenant({"tools": []}, name="云杉数码商城"))
    assert "云杉数码商城" in spec.system_prompt
    assert estimate_tokens(spec.system_prompt) <= ContextConfig().system_budget


def test_entry_classifier_and_owned_values_seams() -> None:
    """9 字段注入面收尾：entry_classifier 按租户 config（缺省关）；owned_values 参数缝 v1 恒空（拍板Ⅳ）。"""
    assert build_agent_spec(_tenant({"tools": []})).entry_classifier is False
    assert build_agent_spec(_tenant({"tools": [], "entry_classifier": True})).entry_classifier is True
    assert build_agent_spec(_tenant({"tools": []})).owned_values == ()
    spec = build_agent_spec(_tenant({"tools": []}), owned_values=["138-0000-0000"])
    assert spec.owned_values == ("138-0000-0000",)

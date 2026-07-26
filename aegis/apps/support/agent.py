"""主 Agent 装配器（M3.8 交付①，plans §4.8——03 §1 依赖倒置的落点）。

prompt/工具集/策略/租户配置全部在此注入，运行时对"客服"一无所知。
AgentSpec 9 字段注入面在此收尾（实况块 #2）：owned_values 每会话参数缝
（v1 恒空，拍板Ⅳ）、entry_classifier 按租户 config（缺省关）。
"""

from __future__ import annotations

from collections.abc import Sequence

from aegis.apps.support.prompts import SYSTEM_PROMPT_TEMPLATE
from aegis.apps.support.tools.coupons import coupon_grant
from aegis.apps.support.tools.logistics import logistics_query
from aegis.apps.support.tools.orders import order_query
from aegis.apps.support.tools.refunds import refund_apply
from aegis.apps.support.tools.tickets import ticket_create
from aegis.core.tenancy import TenantRecord
from aegis.runtime.spec import AgentSpec, ContextConfig, LoopPolicy
from aegis.runtime.tools import ToolDef

ALL_TOOLS: dict[str, ToolDef] = {
    t.name: t for t in (order_query, logistics_query, ticket_create, refund_apply, coupon_grant)
}
"""五工具注册清单（name→ToolDef）。租户白名单从这里点名取用，
点不到的名字=配置错误启动炸；dict 保插入序（specs 顺序=回放确定性一环）。"""


def build_agent_spec(tenant: TenantRecord, *, owned_values: Sequence[str] = ()) -> AgentSpec:
    """按租户配置装配 AgentSpec（§4.8 精确签名，实况块 #2 扩为含用户侧输入）。

    工具面=攻击面：白名单按 config["tools"] 点名、一个不多（给 B 装 refunds
    "反正闸门会拦"是错的——§4.8 陷阱 2）；重复引入用 dict 语义去重保序（陷阱 1）。
    session_token_budget/approval_ttl_s 从租户 config 注入（实况块 #8），其余阈值默认。
    memory_budget=0 显式关长期记忆层（P1 砍出 v1——不调 provider 才是真关闭 D14）。
    owned_values（C23 允许清单）v1 恒空：users 表无 PII 列、数据源属 v2（拍板Ⅳ）。
    """
    config = dict(tenant.config)
    tool_names = [str(n) for n in config.get("tools", [])]
    unknown = sorted(set(tool_names) - set(ALL_TOOLS))
    if unknown:
        raise ValueError(f"租户 {tenant.id} 配置了未知工具：{unknown}——可用：{sorted(ALL_TOOLS)}")
    return AgentSpec(
        system_prompt=SYSTEM_PROMPT_TEMPLATE.format(tenant_name=tenant.name),
        tools=tuple(ALL_TOOLS[n] for n in dict.fromkeys(tool_names)),
        policy=LoopPolicy(
            session_token_budget=int(config.get("session_token_budget", LoopPolicy().session_token_budget)),
            approval_ttl_s=float(config.get("approval_ttl_s", LoopPolicy().approval_ttl_s)),
        ),
        context_config=ContextConfig(memory_budget=0),
        model_tier="standard",
        tenant_config=config,
        owned_values=tuple(owned_values),
        entry_classifier=bool(config.get("entry_classifier", False)),
    )

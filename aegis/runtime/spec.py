"""L2 运行时注入面类型：终止原因 + 循环策略 + 上下文预算（03 §1/§2/§3 的类型落地）。

运行时对"客服"一无所知——prompt/工具/策略/租户配置全部由 L3 经这些类型注入。
M2.1 分三次交付：本文件承载交付①（终止原因/策略/预算）与交付②的 AgentSpec；
工具契约在 tools.py；事件类型与 AgentRuntime 门面随交付③。
校验强度跟着信任边界走：这里是受信代码的配置，用 frozen dataclass + 防呆即可；
LLM 生成的工具参数才需要 pydantic 严校验（03 §4，M2.4）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, get_args

from aegis.gateway.schema import Tier
from aegis.runtime.tools import ToolDef


class TerminationReason(StrEnum):
    """AgentLoop 终止原因全集（03 §2 七类 + C6 的 gateway_rejected）。

    值是稳定的 snake_case 字符串：将进 loop_terminated 事件 payload 与回放断言，
    历史事件一旦落盘，改值 = 破坏重放——test_spec 的值快照会先红。
    GATEWAY_REJECTED 在"七类终止条件"之外：不是循环闸门，而是 L1 上抛的
    确定性拒绝（配置/协议 bug 信号），终止时不走兜底话术（00 §2.2 C6 裁决）。
    """

    COMPLETED = "completed"  # 0 正常完成
    MAX_ITERATIONS = "max_iterations"  # 闸门1 最大轮数
    STEP_TIMEOUT = "step_timeout"  # 闸门2 单步超时
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"  # 闸门3 会话 token 预算
    REPEATED_CALLS = "repeated_calls"  # 闸门4 重复调用
    PROTOCOL_VIOLATION = "protocol_violation"  # 闸门5 协议违规
    CANCELLED = "cancelled"  # 闸门6 取消 / HITL 拒绝或超时
    GATEWAY_REJECTED = "gateway_rejected"  # 七类之外：L1 确定性拒绝


TERMINATION_GATES: frozenset[TerminationReason] = frozenset(TerminationReason) - {
    TerminationReason.COMPLETED,
    TerminationReason.GATEWAY_REJECTED,
}
"""六道终止闸门（00 §2.2 术语口径：7 类里除正常完成外的 6 项防护）。
gateway_rejected 不在七类内，自然不算闸门。测试钉死 len == 6 防术语漂移。"""


@dataclass(frozen=True, slots=True)
class LoopPolicy:
    """循环约束——03 §2 终止条件表"默认阈值"列的家。

    frozen：策略在一次 run 内不许中途改动，要变换新实例（回放一致性依赖此语义）。
    只承载闸门 1–5 的阈值；闸门 6（取消/HITL）由外部信号与审批单 expires_at 触发（M2.9）。
    llm_step_timeout_s 即传给网关的 deadline——与 L1 三段超时的嵌套约束由
    deadline 传播保证，不做人肉算术校验（C1 裁决）。
    session_token_budget 的生产值由 L3 从租户配置注入（M3.1），默认值只服务
    运行时测试/演示；计数用 core/tokens.py 估算值（C25：护栏用估算、账单用实测）。
    tool_step_timeout_s 是循环级默认上限，单工具 ToolDef.timeout 更严时取更严（M2.4）。
    """

    max_iterations: int = 10
    llm_step_timeout_s: float = 90.0
    tool_step_timeout_s: float = 30.0
    session_token_budget: int = 50_000
    repeat_call_limit: int = 3
    protocol_retry_limit: int = 2

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError(f"max_iterations 须 ≥1，得到 {self.max_iterations}")
        if self.llm_step_timeout_s <= 0:
            raise ValueError(f"llm_step_timeout_s 须 >0，得到 {self.llm_step_timeout_s}")
        if self.tool_step_timeout_s <= 0:
            raise ValueError(f"tool_step_timeout_s 须 >0，得到 {self.tool_step_timeout_s}")
        if self.session_token_budget < 1:
            raise ValueError(f"session_token_budget 须 ≥1，得到 {self.session_token_budget}")
        if self.repeat_call_limit < 1:
            raise ValueError(f"repeat_call_limit 须 ≥1，得到 {self.repeat_call_limit}")
        if self.protocol_retry_limit < 0:
            raise ValueError(f"protocol_retry_limit 须 ≥0，得到 {self.protocol_retry_limit}")


@dataclass(frozen=True, slots=True)
class ContextConfig:
    """六层上下文预算（03 §3 表）。单位 token，估算口径同 LoopPolicy。

    system 与 output_reserve 不许为 0（system 固定不可挤占；没有输出余量的循环无意义）；
    中间四层允许 0 = 显式关闭该层。长期记忆与本轮检索两层在 M2 只有注入接口，
    实现随 M3 RAG（§10.1 #7）。
    """

    system_budget: int = 1_500
    memory_budget: int = 1_000
    history_budget: int = 4_000
    retrieval_budget: int = 3_000
    tool_results_budget: int = 3_000
    output_reserve: int = 4_000

    def __post_init__(self) -> None:
        if self.system_budget < 1:
            raise ValueError(f"system_budget 须 ≥1，得到 {self.system_budget}")
        if self.output_reserve < 1:
            raise ValueError(f"output_reserve 须 ≥1，得到 {self.output_reserve}")
        for name in ("memory_budget", "history_budget", "retrieval_budget", "tool_results_budget"):
            value: int = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} 须 ≥0，得到 {value}")

    @property
    def input_total(self) -> int:
        """输入侧五层合计（不含输出余量），默认 12_500——M2.5 编译器与 M2.7 对账用。"""
        return self.system_budget + self.memory_budget + self.history_budget + self.retrieval_budget + self.tool_results_budget


class SubAgentPolicy(StrEnum):
    """v1 恒 DISABLED——为 ADR-002"只读子 Agent 并行调查"（v2）预留的接口位。

    只有一个成员是有意的：测试钉死 len==1，v2 想加成员先让测试红、重过 ADR-002。
    """

    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """L3 注入运行时的全部内容（03 §1）——运行时对"客服"一无所知。

    tools 用 tuple 不用 list：注入面是冻结的（一次 run 内不可变，回放一致性依赖）。
    tenant_config 对运行时不透明：只透传给 risk_policy 等注入点，解释权在 L3——
    依赖倒置的落点，运行时不知道 approval_threshold 是什么。
    model_tier 复用 L1 的 Tier 字面量（gateway/schema.py）：档位语义两层同一事实源；
    Literal 只防静态，get_args 运行时防线拦 L3 从配置读出的裸字符串。
    """

    system_prompt: str
    tools: tuple[ToolDef, ...] = ()
    policy: LoopPolicy = LoopPolicy()
    context_config: ContextConfig = ContextConfig()
    model_tier: Tier = "standard"
    sub_agent_policy: SubAgentPolicy = SubAgentPolicy.DISABLED
    tenant_config: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.system_prompt.strip():
            raise ValueError("system_prompt 不许为空——没有平台规则的 Agent 不许起跑")
        if self.model_tier not in get_args(Tier):
            raise ValueError(f"model_tier 须为 {get_args(Tier)} 之一，得到 {self.model_tier!r}")
        names = [t.name for t in self.tools]
        if len(names) != len(set(names)):
            dupes = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"工具名重复：{dupes}——dispatch 表将无法唯一路由")

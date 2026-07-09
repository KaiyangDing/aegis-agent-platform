"""工具契约：ToolDef（工具的完整说明书）与 ToolContext（运行时注入的身份）。

03 §4 的类型落地（M2.1 交付②）。核心安全分野：LLM 只能提供业务参数
（order_id 这类"查询条件"），身份（tenant_id/user_id）由运行时注入 ctx、
模型不可控——水平越权的第一道防线在类型签名上就成立。
@tool 装饰器（从函数自动生成 ToolDef、剔除 ctx 参数、C15 注册期防呆）随 M2.3 交付。
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SideEffect(StrEnum):
    """读写标记（评审 X2）：恢复期"仅读可重发"由此机器判定，不靠人读文档。"""

    READ = "read"
    WRITE = "write"


_TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
"""OpenAI 兼容 tool schema 对函数名的硬约束（M1.4 的线格式现实），构造期就拦住。"""


@dataclass(frozen=True, slots=True)
class ToolContext:
    """运行时注入给工具实现的身份与关联 id——全部 LLM 不可控。

    tool_call_id 即 write-ahead 落盘的 tool_call 事件 id（03 §4 ④）：
    工具实现把它作为幂等键透传给下游（M3.7 退款服务按键去重）。
    id 三层模型见 00 §2.2 X5：trace_id ≡ session_id，run_id 每次循环启动新生成。
    """

    tenant_id: str
    user_id: str
    session_id: str
    run_id: str
    tool_call_id: str

    def __post_init__(self) -> None:
        for name in ("tenant_id", "user_id", "session_id", "run_id", "tool_call_id"):
            if not getattr(self, name):
                raise ValueError(f"{name} 不许为空——空租户/空幂等键意味着隔离或去重已失效")


RiskPolicy = Callable[[Any, Mapping[str, Any]], bool]
"""风险闸门谓词：(已校验的工具参数, 租户配置) -> 是否需要 HITL 审批。
参数的真实类型是 M2.3 装饰器为各工具生成的 args 模型，运行时无法静态枚举，故 Any。"""


@dataclass(frozen=True, slots=True)
class ToolDef:
    """一个工具的完整说明书：给 LLM 看的、给执行器用的、给恢复期读的——单一事实源。

    side_effect 无默认值：是读是写必须显式声明（C15 防呆的类型层，
    完整防呆——写工具须有 risk_policy 或显式豁免——在 M2.3 注册期）。
    timeout_s=None 表示继承 LoopPolicy.tool_step_timeout_s，显式值与循环级上限
    取更严（M2.4 接电）。写工具 retries 恒为 0：写操作绝不自动重试（03 §4 ⑤），
    幂等靠 write-ahead 键透传而不是"再试一次"。
    """

    name: str
    description: str
    handler: Callable[..., Awaitable[Any]]
    side_effect: SideEffect
    parameters_schema: Mapping[str, Any] = field(default_factory=dict)
    risk_policy: RiskPolicy | None = None
    timeout_s: float | None = None
    retries: int = 0

    def __post_init__(self) -> None:
        if not _TOOL_NAME_RE.fullmatch(self.name):
            raise ValueError(f"工具名不合法（须匹配 LLM tool schema 硬约束），得到 {self.name!r}")
        if not self.description.strip():
            raise ValueError(f"{self.name}: description 不许为空——它是给模型的说明书，空说明书=盲选工具")
        if self.timeout_s is not None and self.timeout_s <= 0:
            raise ValueError(f"{self.name}: timeout_s 须 >0 或 None（继承循环级默认），得到 {self.timeout_s}")
        if self.retries < 0:
            raise ValueError(f"{self.name}: retries 须 ≥0，得到 {self.retries}")
        if self.side_effect is SideEffect.WRITE and self.retries > 0:
            raise ValueError(f"{self.name}: 写工具禁止自动重试（03 §4），retries 须为 0")

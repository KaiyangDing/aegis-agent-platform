"""ToolExecutor：工具调用的七步生命周期（03 §4）。

交付①覆盖前厅（校验 → 可用性 → 风险闸门）与连败禁用；
write-ahead 与执行随交付②，规范化与事件闭环随交付③。
执行器从不向循环抛业务异常——工具世界的一切结局编码成 ToolOutcome，
异常只留给基础设施故障。每个 run 一个实例（连败账与禁用集的作用域）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from aegis.runtime.tools import ToolRegistry


class OutcomeKind(StrEnum):
    """工具调用的五种结局。值进事件 payload 与回放断言，快照测试钉死。"""

    OK = "ok"  # 成功：结果已入事件流（交付③接电）
    ERROR = "error"  # 失败：错误文本回填给模型，它通常能自我修正
    RESULT_UNKNOWN = "result_unknown"  # 写工具超时/结果不明：禁止重试话术（X1，交付②接电）
    NEEDS_APPROVAL = "needs_approval"  # 风险闸门命中：挂起流程由 M2.9 接管
    DISABLED = "disabled"  # 本轮连败禁用：改道提示


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    """一次工具调用的结局。content 是回填给模型的观察结果——它是对话的一部分。"""

    kind: OutcomeKind
    tool_name: str
    content: str
    tool_call_id: str | None = None  # write-ahead 之后才有（交付②起填充）


class ToolExecutor:
    """每个 run 一个实例：连败计数与禁用集的"本轮"就是一次 run 的寿命。"""

    def __init__(
        self,
        tools: ToolRegistry,
        tenant_config: Mapping[str, Any],
        *,
        fail_streak_limit: int = 2,
    ) -> None:
        self._tools = tools
        self._tenant_config = tenant_config
        self._fail_streak_limit = fail_streak_limit
        self._fail_streaks: dict[str, int] = {}
        self._disabled: set[str] = set()

    async def execute(self, name: str, arguments_json: str) -> ToolOutcome:
        tool = self._tools.get(name)
        if tool is None:
            # 幻觉工具名：没有工具可禁用，不进连败账；点名可用工具帮模型改口
            available = "、".join(t.name for t in self._tools.specs())
            return ToolOutcome(OutcomeKind.ERROR, name, f"工具 {name} 不存在——可用工具：{available}")
        if name in self._disabled:
            return ToolOutcome(
                OutcomeKind.DISABLED,
                name,
                f"工具 {name} 本轮已禁用（连续失败 {self._fail_streak_limit} 次），请改用其他方式或告知用户",
            )

        # 生命周期① 严格校验：lax 模式 + extra=forbid——宽容度与导出 schema 一致，
        # 说明书答应的（数字字符串）验货必须认；说明书没有的（幻觉参数）零容忍
        try:
            raw = json.loads(arguments_json)
        except json.JSONDecodeError as e:
            return self._fail(name, f"参数不是合法 JSON：{e}")
        if not isinstance(raw, dict):
            return self._fail(name, "参数必须是 JSON 对象（键值对），不是数组或标量")
        args: Any = raw
        if tool.args_model is not None:
            try:
                args = tool.args_model.model_validate(raw)
            except ValidationError as e:
                return self._fail(name, f"参数校验失败：{e}")

        # 生命周期③ 风险闸门：确定性安全闸门，fail-closed——评估不了绝不放行
        if tool.risk_policy is not None:
            try:
                needs_approval = tool.risk_policy(args, self._tenant_config)
            except Exception as e:
                return self._fail(name, f"风险评估失败，操作未执行（安全闸门 fail-closed）：{e}")
            if needs_approval:
                return ToolOutcome(
                    OutcomeKind.NEEDS_APPROVAL, name, f"操作命中风险闸门，需人工审批后执行（工具 {name}）"
                )

        raise NotImplementedError("write-ahead 与执行随 M2.4 交付②接管")

    def _fail(self, name: str, content: str) -> ToolOutcome:
        """记连败账：达到上限即禁用，并在当次回填里宣告——模型立刻知道该改道。"""
        streak = self._fail_streaks.get(name, 0) + 1
        self._fail_streaks[name] = streak
        if streak >= self._fail_streak_limit:
            self._disabled.add(name)
            content += f"；该工具连续失败 {streak} 次，本轮已禁用"
        return ToolOutcome(OutcomeKind.ERROR, name, content)

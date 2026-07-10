"""ToolExecutor：工具调用的七步生命周期（03 §4）。

交付①覆盖前厅（校验 → 可用性 → 风险闸门）与连败禁用；
write-ahead 与执行随交付②，规范化与事件闭环随交付③。
执行器从不向循环抛业务异常——工具世界的一切结局编码成 ToolOutcome，
异常只留给基础设施故障。每个 run 一个实例（连败账与禁用集的作用域）。
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.tools import SideEffect, ToolContext, ToolRegistry


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


class EventSink(Protocol):
    """执行器眼中的事件写入器（按形状声明，EventWriter 天然满足）。

    append 声明为 async def——它是真协程（await 一次拿一个值），
    与 GatewayLike.complete 的 def+AsyncGenerator（调用即得流）形成对照。
    """

    @property
    def session_id(self) -> str: ...

    @property
    def run_id(self) -> str: ...

    async def append(self, event_type: EventType, payload: Mapping[str, Any]) -> AgentEvent: ...


def _kwargs(args: Any) -> dict[str, Any]:
    """把已校验参数摊开成 handler 的关键字参数——保留真类型（Decimal 不许降级成 float）。"""
    if isinstance(args, BaseModel):
        return {field: getattr(args, field) for field in type(args).model_fields}
    return dict(args)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


class ToolExecutor:
    """每个 run 一个实例：连败计数与禁用集的"本轮"就是一次 run 的寿命。"""

    def __init__(
        self,
        tools: ToolRegistry,
        events: EventSink,
        *,
        tenant_id: str,
        user_id: str,
        tenant_config: Mapping[str, Any],
        default_timeout_s: float = 30.0,
        fail_streak_limit: int = 2,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._tools = tools
        self._events = events
        self._tenant_id = tenant_id
        self._user_id = user_id
        self._tenant_config = tenant_config
        self._default_timeout_s = default_timeout_s
        self._fail_streak_limit = fail_streak_limit
        self._sleep = sleep
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

        # ④ write-ahead：tool_call 事实先落盘，插入成功是执行副作用的前置（C2）；
        #    事件 id 即幂等键，经 ctx 透传给工具实现（03 §4）
        call_event = await self._events.append(
            EventType.TOOL_CALL,
            {
                "tool_name": name,
                "args": args.model_dump(mode="json") if isinstance(args, BaseModel) else args,
            },
        )
        ctx = ToolContext(
            tenant_id=self._tenant_id,
            user_id=self._user_id,
            session_id=self._events.session_id,
            run_id=self._events.run_id,
            tool_call_id=call_event.id,
        )

        # ⑤ 超时取更严；读可退避重试、写绝不（attempts 按 side_effect 分支是第一道保险，
        #    ToolDef"写 retries 恒 0"的类型不变量是第二道）
        timeout_s = self._default_timeout_s if tool.timeout_s is None else min(tool.timeout_s, self._default_timeout_s)
        attempts_allowed = 1 + (tool.retries if tool.side_effect is SideEffect.READ else 0)
        kwargs = _kwargs(args)
        started = time.monotonic()
        attempt = 0
        while True:
            attempt += 1
            try:
                async with asyncio.timeout(timeout_s):
                    result = await tool.handler(ctx, **kwargs)
                break
            except TimeoutError:
                if tool.side_effect is SideEffect.WRITE:
                    # X1：写超时=结果不明，副作用可能已在下游生效；模型若自发重试会生成
                    # 新幂等键，下游去重当场失效——话术必须封死重试、引导查询确认
                    await self._append_error(call_event.id, "执行超时，结果不明", started, attempt - 1)
                    return ToolOutcome(
                        OutcomeKind.RESULT_UNKNOWN,
                        name,
                        f"操作结果未知：{name} 执行超时，副作用可能已在下游生效。"
                        "禁止重试该操作——请先用查询类工具确认实际状态，再决定下一步。",
                        tool_call_id=call_event.id,
                    )
                if attempt >= attempts_allowed:
                    await self._append_error(call_event.id, f"执行超时（>{timeout_s:g}s）", started, attempt - 1)
                    return self._fail(name, f"工具执行超时（>{timeout_s:g}s）", tool_call_id=call_event.id)
                await self._sleep(0.2 * attempt)
            except Exception as e:
                if attempt >= attempts_allowed:
                    await self._append_error(call_event.id, str(e), started, attempt - 1)
                    return self._fail(name, f"工具执行失败：{e}", tool_call_id=call_event.id)
                await self._sleep(0.2 * attempt)

        # 成功：连败账清零；结果原文入事件流（X4），规范化随交付③
        self._fail_streaks.pop(name, None)
        await self._events.append(
            EventType.TOOL_RESULT,
            {
                "tool_call_id": call_event.id,
                "result": result,
                "latency_ms": _elapsed_ms(started),  # C31 回放等价断言的豁免字段：记录、不比对
                "retry_count": attempt - 1,
            },
        )
        return ToolOutcome(
            OutcomeKind.OK,
            name,
            json.dumps(result, ensure_ascii=False, default=str),
            tool_call_id=call_event.id,
        )

    def _fail(self, name: str, content: str, *, tool_call_id: str | None = None) -> ToolOutcome:
        """记连败账：达到上限即禁用，并在当次回填里宣告——模型立刻知道该改道。"""
        streak = self._fail_streaks.get(name, 0) + 1
        self._fail_streaks[name] = streak
        if streak >= self._fail_streak_limit:
            self._disabled.add(name)
            content += f"；该工具连续失败 {streak} 次，本轮已禁用"
        return ToolOutcome(OutcomeKind.ERROR, name, content, tool_call_id=tool_call_id)

    async def _append_error(self, tool_call_id: str, error: str, started: float, retry_count: int) -> None:
        await self._events.append(
            EventType.TOOL_ERROR,
            {
                "tool_call_id": tool_call_id,
                "error": error,
                "latency_ms": _elapsed_ms(started),
                "retry_count": retry_count,
            },
        )

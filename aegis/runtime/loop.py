"""AgentLoop：循环骨架与终止闸门的家（03 §2，M2.7 总装）。

命名分工见 runtime.py 模块 docstring：AgentRuntime 是对外门面，本模块是内部驱动，
对 L3 不可见。七类终止（+GATEWAY_REJECTED 在七类外）的接电分布：
骨架与闸门 #1/#3/#5/#6 随交付①，工具分支与闸门 #4 随交付②，
网关异常矩阵（闸门 #2 的 LLM 半边、C6）随交付③。
话术全部收敛为模块级常量（D13）：测试断子串、M2.8 出口防护有单点。
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from aegis.core.tokens import estimate_tokens
from aegis.gateway.schema import (
    LLMRequest,
    Message,
    StopChunk,
    TextDelta,
    ToolCall,
    ToolCallChunk,
    ToolSpec,
    UsageChunk,
)
from aegis.runtime.context import ContextBuilder
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.executor import ToolExecutor
from aegis.runtime.spec import AgentSpec, TerminationReason
from aegis.runtime.store import EventWriter

if TYPE_CHECKING:
    # 只为类型：runtime.py 反向 import 本模块组装 AgentLoop，真 import 会成环
    from aegis.runtime.runtime import GatewayLike

# ---- 话术常量（D13）：兜底/提示单点收口，测试断子串、M2.8 出口防护有的放矢 ----

FALLBACK_MAX_ITERATIONS = "本次处理步骤较多仍未完成，为避免无效循环先停在这里，已为你转人工跟进。"
FALLBACK_STEP_FAILED = "上游服务暂时不可用，这一步已作废；请稍后重试，或联系人工客服。"
FALLBACK_BUDGET = "本次会话的 token 预算已用尽，为不影响回答质量不做静默截断；请开启新会话或转人工处理。"
FALLBACK_REPEATED = "检测到对同一操作的重复尝试已达上限，本次处理先停止；请换一种问法或转人工处理。"
FALLBACK_PROTOCOL = "模型连续多次未按协议输出，本次处理已终止；请重试或转人工处理。"
PROMPT_REPEAT_BREAK = (
    "你已连续 {limit} 次以完全相同的参数调用同一工具，本次调用未被执行。"
    "请换一个工具或换一组参数；若确实无计可施，请直接向用户说明情况。"
)
PROMPT_PROTOCOL_RETRY = (
    "你的上一条输出不符合协议：需要非空的文字回答，或与停止原因一致的工具调用。"
    "请重新输出——要么给出面向用户的回答，要么发起一个有效的工具调用。"
)


def canonical_json(arguments_json: str) -> str:
    """D4：语义等价归一——sort_keys + 紧凑分隔符 + ensure_ascii=False（与仓库 dumps 口径一致）。

    坏 JSON 以原始字符串为规范形：网关不解析坏参数（schema.py:29-30），
    逐字重复的坏参数也是重复。消费方是闸门 #4（交付②）。
    """
    try:
        parsed = json.loads(arguments_json)
    except json.JSONDecodeError:
        return arguments_json
    return json.dumps(parsed, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class _Tap:
    """EventSink 实现（D16）：append 委托真写入器，同时把事件排进待产队列。

    loop 与 executor/builder 共用同一个 _Tap——所有事件都被捕获，run() 在固定点
    drain 外流，yield 序 ≡ seq 序（I4：产出集合 = 落盘集合，逐条不漏）。
    """

    def __init__(self, writer: EventWriter) -> None:
        self._writer = writer
        self._pending: deque[AgentEvent] = deque()

    @property
    def session_id(self) -> str:
        return self._writer.session_id

    @property
    def run_id(self) -> str:
        return self._writer.run_id

    async def append(self, event_type: EventType, payload: Mapping[str, Any]) -> AgentEvent:
        event = await self._writer.append(event_type, payload)
        self._pending.append(event)
        return event

    def drain(self) -> list[AgentEvent]:
        """取走并清空待产队列（先进先出，即 seq 序）。"""
        out = list(self._pending)
        self._pending.clear()
        return out


@dataclass(frozen=True, slots=True)
class _LLMTurn:
    """一次 LLM 步的聚合结果：四类 chunk 收拢成一个可分类的值对象。"""

    text: str
    tool_calls: tuple[ToolCall, ...]
    stop_reason: str
    model: str
    usage_prompt: int
    usage_completion: int
    cached: bool


def _estimate_messages(messages: Sequence[Message]) -> int:
    """D8 输入侧估算：各 content + 各 tool_calls 参数原文（与 context.py D16 同口径，C25 一把尺）。"""
    return sum(
        estimate_tokens(m.content) + sum(estimate_tokens(tc.arguments_json) for tc in m.tool_calls) for m in messages
    )


def _estimate_turn_output(turn: _LLMTurn) -> int:
    """D8 输出侧估算：聚合文本 + 各 arguments_json。"""
    return estimate_tokens(turn.text) + sum(estimate_tokens(tc.arguments_json) for tc in turn.tool_calls)


class AgentLoop:
    """内部驱动：组装上下文 → 调网关 → 解析分支 → 工具 → 下一轮，直至七类终止之一。

    每次 run 一个实例（同 ToolExecutor/EventWriter 惯例）：违规计数、重复检测、
    token 累计都是"本 run"作用域的状态。阈值全部来自 LoopPolicy——本模块零魔法数字（I1）。
    """

    def __init__(
        self,
        spec: AgentSpec,
        gateway: GatewayLike,
        events: _Tap,
        builder: ContextBuilder,
        executor: ToolExecutor,
        *,
        tenant_id: str,
        token_seed: int,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        self._spec = spec
        self._gateway = gateway  # 已是 main 作用域视图（D15：摘要走各自的道，勿混）
        self._events = events
        self._builder = builder
        self._executor = executor
        self._tenant_id = tenant_id
        self._cancel_event = cancel_event
        self._policy = spec.policy
        # 工具说明书一次转换：顺序 = spec.tools 注入序（回放确定性的一环）
        self._tool_specs = [
            ToolSpec(name=t.name, description=t.description, parameters=dict(t.parameters_schema)) for t in spec.tools
        ]
        # ——本 run 的循环状态——
        self._iteration = 0
        self._tokens_used = token_seed  # D8 会话级口径：起点 = 历史事件重建的估算累计
        self._violations = 0  # 闸门 #5：连续违规计数，合法输出清零
        self._turns: list[Message] = []  # 本 run 工作消息序列，经 build(working=…) 进 prompt
        self._repeat_key: tuple[str, str] | None = None  # 闸门 #4 状态（交付②消费）
        self._repeat_streak = 0

    async def run(self, user_input: str) -> AsyncIterator[AgentEvent]:
        """驱动循环至终止。产出事件 ≡ 本 run 落盘事件，且 yield 序 ≡ seq 序（I4）。"""
        # user_message 恒为首事件（I5；D19——单写者不变量下由 loop 写入，API 层不旁路）
        await self._events.append(EventType.USER_MESSAGE, {"content": user_input})
        for event in self._events.drain():
            yield event
        # M2.8 挂点①：入口守卫（注入规则库 + 可疑度分类）将插在这里——本步只留位

        while True:
            # 闸门 #6 取消（P1）：每次 LLM 调用前查一次；工具前的检查点在 _run_tools（交付②）
            if self._cancel_event is not None and self._cancel_event.is_set():
                await self._terminate(
                    TerminationReason.CANCELLED,
                    detail="收到取消信号",
                    fallback=None,  # 用户主动取消无需道歉文（D13）
                )
                for event in self._events.drain():
                    yield event
                return

            # 闸门 #1 最大轮数（D17）：已完成 n 次调用、再欲发起下一次即终止
            if self._iteration >= self._policy.max_iterations:
                await self._terminate(
                    TerminationReason.MAX_ITERATIONS,
                    detail=f"已完成 {self._iteration} 次 LLM 调用，达 max_iterations 上限",
                    fallback=FALLBACK_MAX_ITERATIONS,
                )
                for event in self._events.drain():
                    yield event
                return
            self._iteration += 1

            # 组装上下文（M2.5）：滚动摘要可能在 build 内发 summary_updated——随后一并外流
            messages = await self._builder.build(
                system_prompt=self._spec.system_prompt,
                user_input=user_input,
                working=self._turns,
            )
            input_est = _estimate_messages(messages)

            # 闸门 #3 会话 token 预算（D8）：调用前查——不打注定超预算的半截请求
            if self._tokens_used + input_est > self._policy.session_token_budget:
                await self._terminate(
                    TerminationReason.TOKEN_BUDGET_EXCEEDED,
                    detail=(
                        f"累计估算 {self._tokens_used} + 本次输入 {input_est} "
                        f"> session_token_budget={self._policy.session_token_budget}"
                    ),
                    fallback=FALLBACK_BUDGET,  # 明确告知，不做静默截断（03:50）
                )
                for event in self._events.drain():
                    yield event
                return

            await self._events.append(
                EventType.LLM_CALL,
                {"iteration": self._iteration, "tier": self._spec.model_tier, "input_tokens_est": input_est},
            )
            for event in self._events.drain():
                yield event

            started = time.monotonic()
            turn = await self._llm_step(messages)  # 交付③：网关异常矩阵（§4.4）将包在这一步外
            output_est = _estimate_turn_output(turn)
            await self._events.append(
                EventType.LLM_RESULT,
                {
                    "iteration": self._iteration,
                    "status": "ok",
                    "text": turn.text,
                    "tool_calls": [
                        {"id": tc.id, "name": tc.name, "arguments_json": tc.arguments_json} for tc in turn.tool_calls
                    ],
                    "stop_reason": turn.stop_reason,
                    "model": turn.model,
                    "usage": {"prompt_tokens": turn.usage_prompt, "completion_tokens": turn.usage_completion},
                    "cached": turn.cached,
                    "output_tokens_est": output_est,
                    "latency_ms": int((time.monotonic() - started) * 1000),  # C31 豁免字段
                },
            )
            self._tokens_used += input_est + output_est
            for event in self._events.drain():
                yield event

            kind = self._classify(turn)
            if kind == "violation":
                self._violations += 1
                if self._violations > self._policy.protocol_retry_limit:
                    await self._terminate(
                        TerminationReason.PROTOCOL_VIOLATION,
                        detail=f"连续 {self._violations} 次协议违规，超过纠错上限",
                        fallback=FALLBACK_PROTOCOL,
                    )
                    for event in self._events.drain():
                        yield event
                    return
                # D7：纠错提示以 user 消息进工作序列——system 层固定不可挤占（03 §3）
                self._turns.append(Message(role="user", content=PROMPT_PROTOCOL_RETRY))
                continue

            self._violations = 0  # 合法输出清零（连续计数语义）
            if kind == "text":
                await self._finish_text(turn)
                await self._terminate(
                    TerminationReason.COMPLETED,
                    detail=f"stop_reason={turn.stop_reason}",
                    fallback=None,  # 正常回复已在 _finish_text 发出
                )
                for event in self._events.drain():
                    yield event
                return

            # tools 分支：assistant(tool_calls) 消息先入工作序列（协议要求先声明后回填）
            self._turns.append(Message(role="assistant", content=turn.text, tool_calls=list(turn.tool_calls)))
            reason = await self._run_tools(turn)
            for event in self._events.drain():
                yield event
            if reason is not None:
                return

    def _classify(self, turn: _LLMTurn) -> Literal["text", "tools", "violation"]:
        """三分支判定（D7/D18）。幻觉工具名不在此判——那要查注册表，归 _run_tools（D6）。"""
        if turn.stop_reason == "tool_calls" and not turn.tool_calls:
            return "violation"  # D7②：声明了工具停却一个调用都没给
        if turn.tool_calls:
            return "tools"
        if turn.text.strip():
            return "text"  # 含 D18：max_tokens 截断但文本非空按完成（截断是预算现实不是协议错误）
        return "violation"  # D7①：无工具调用且文本为空

    async def _llm_step(self, messages: list[Message]) -> _LLMTurn:
        """发一次主循环 LLM 调用并聚合四类 chunk。

        闸门 #2 的 LLM 半边就是 deadline_s 传播（C1/I2）：不包 asyncio.timeout，
        嵌套约束由 L1 三段超时（connect 5s / 首块 25s / 空闲 30s）与 deadline 机制保证。
        """
        request = LLMRequest(
            tier=self._spec.model_tier,
            messages=messages,
            tools=self._tool_specs,
            tenant_id=self._tenant_id,
            session_id=self._events.session_id,  # 回放匹配键第一段（m2.6 对齐要求：必带）
            deadline_s=self._policy.llm_step_timeout_s,
            max_tokens=self._spec.context_config.output_reserve,  # D3：输出上限即余量层预算
        )
        parts: list[str] = []
        calls: list[ToolCall] = []
        usage: UsageChunk | None = None
        stop: StopChunk | None = None
        stream = self._gateway.complete(request)  # def：调用即得 async 生成器，不 await（§7 坑 1）
        async with aclosing(stream):  # 提前退出时把 GeneratorExit 送进生成器，归还底层连接
            async for chunk in stream:
                if isinstance(chunk, TextDelta):
                    parts.append(chunk.text)
                elif isinstance(chunk, ToolCallChunk):
                    calls.append(chunk.tool_call)
                elif isinstance(chunk, UsageChunk):
                    usage = chunk
                elif isinstance(chunk, StopChunk):
                    stop = chunk
        if stop is None:
            # 契约上不可能（网关顺序不变量以 StopChunk 收尾）；防御性按违规形状返回，
            # 让闸门 #5 的纠错路径接手，而不是在这里编造一个结局
            return _LLMTurn(
                text="",
                tool_calls=(),
                stop_reason="end_turn",
                model="",
                usage_prompt=0,
                usage_completion=0,
                cached=False,
            )
        return _LLMTurn(
            text="".join(parts),
            tool_calls=tuple(calls),
            stop_reason=stop.reason,
            model=usage.model if usage else "",
            usage_prompt=usage.prompt_tokens if usage else 0,
            usage_completion=usage.completion_tokens if usage else 0,
            cached=bool(usage and usage.cached),
        )

    async def _run_tools(self, turn: _LLMTurn) -> TerminationReason | None:
        """工具分支：五结局映射 + 闸门 #4 重复检测 + D6 幻觉计数（交付②接电）。"""
        raise NotImplementedError("工具分支随 M2.7 交付②接电")

    async def _finish_text(self, turn: _LLMTurn) -> None:
        """文本收尾单点（M2.8 挂点③：流式句子缓冲与终局复检都将挂这里）。"""
        await self._events.append(
            EventType.ASSISTANT_MESSAGE,
            {"content": turn.text, "token_usage": turn.usage_completion},
        )

    async def _terminate(
        self,
        reason: TerminationReason,
        *,
        detail: str,
        fallback: str | None,
        cause: str | None = None,
    ) -> None:
        """终止收口单点（D14）：先兜底话术（如有），再 loop_terminated 作为 run 末事件（I7）。

        cause 只在网关异常映射时携带（§4.4，交付③）——三级预算同因异层等场景靠它区分。
        payload 一律 .value（§7 坑 9：断言/构造两侧混用枚举成员与值会漂）。
        """
        if fallback is not None:
            await self._events.append(EventType.ASSISTANT_MESSAGE, {"content": fallback})
        payload: dict[str, Any] = {"reason": reason.value, "iteration": self._iteration, "detail": detail}
        if cause is not None:
            payload["cause"] = cause
        await self._events.append(EventType.LOOP_TERMINATED, payload)

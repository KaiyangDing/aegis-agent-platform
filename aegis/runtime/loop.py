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
import logging
import time
from collections import deque
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from aegis.core.tokens import estimate_tokens
from aegis.gateway.errors import (
    BudgetExceeded,
    GatewayExhausted,
    GatewayOverloadedError,
    GatewayRejected,
    GatewayStreamInterrupted,
    TenantQuotaExceeded,
)
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
from aegis.runtime.executor import OutcomeKind, ToolExecutor
from aegis.runtime.guardrails import (
    REFUSAL_TEMPLATE,
    SAFE_REPLY,
    UNTRUSTED_NOTICE,
    Guardrails,
    entry_audit_payload,
    output_audit_payload,
    wrap_untrusted,
)
from aegis.runtime.spec import AgentSpec, TerminationReason
from aegis.runtime.store import ApprovalStore, EventWriter, RunState, SessionStateStore

logger = logging.getLogger(__name__)

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


class _Suspended:
    """挂起哨兵（D2）：run 干净收尾但不终止——无 loop_terminated，锁释放后进程可下线。"""


_SUSPENDED = _Suspended()


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


def _discard_note(base: str, total: int, index: int) -> str:
    """D20：工具序列中途终止时，把被弃置的剩余调用数写进 detail 留痕。"""
    discarded = total - index - 1
    return f"{base}；弃置本轮剩余 {discarded} 个调用" if discarded else base


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
        approvals: ApprovalStore,
        session_state: SessionStateStore,
        guards: Guardrails | None = None,
    ) -> None:
        self._spec = spec
        self._gateway = gateway  # 已是 main 作用域视图（D15：摘要走各自的道，勿混）
        self._events = events
        self._builder = builder
        self._executor = executor
        self._tenant_id = tenant_id
        self._cancel_event = cancel_event
        self._approvals = approvals
        self._session_state = session_state
        self._guards = guards if guards is not None else Guardrails()  # 未注入 = 纯规则库（分类器归组装方）
        # M2.8 D5：不可信包裹的 system 层声明恒随 prompt——此处拼接一次，spec.system_prompt
        # 本体不动；FakeGateway 匹配键不含 prompt 哈希，既有 cassette 不失配
        self._system_prompt = f"{spec.system_prompt}\n\n{UNTRUSTED_NOTICE}"
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

    async def run(self, user_input: str) -> AsyncGenerator[AgentEvent]:
        """驱动循环至终止。产出事件 ≡ 本 run 落盘事件，且 yield 序 ≡ seq 序（I4）。"""
        # user_message 恒为首事件（I5；D19——单写者不变量下由 loop 写入，API 层不旁路）
        await self._events.append(EventType.USER_MESSAGE, {"content": user_input})
        for event in self._events.drain():
            yield event
        # M2.8 挂点①：入口守卫——HIGH 拒答（不调 LLM）/ MEDIUM 打标 / fail-open 只审计
        verdict = await self._guards.check_input(user_input)
        entry_payload = entry_audit_payload(verdict)
        if entry_payload is not None:
            await self._events.append(EventType.GUARDRAIL_TRIGGERED, entry_payload)
        if verdict.refuse:
            await self._terminate(
                TerminationReason.COMPLETED,  # D10：防线不是第七道闸门，拒答是正常完成
                detail=f"入口守卫拒答：rules={list(verdict.matched_rules)}",
                fallback=REFUSAL_TEMPLATE,
            )
            for event in self._events.drain():
                yield event
            return
        for event in self._events.drain():
            yield event
        async for event in self._main_loop(user_input, entry_notice=verdict.notice):
            yield event

    async def resume_run(self, user_input: str, working: Sequence[Message]) -> AsyncGenerator[AgentEvent]:
        """恢复续跑入口（M2.9，K2② 定案）：不写 user_message（原输入已在旧 run 落盘）、
        不过入口守卫（历史输入挂起前已检）、工作序列由恢复单入口从事件流重建注入，
        主循环与 run() 完全同一条路径——M2.10 崩溃恢复复用本入口（计划内恢复 =
        灾难恢复同路径，03:161）。iteration 从 0 起：闸门 #1 是单 run 界，恢复次数
        上限归 M2.10 的 recovery_count（C9）。"""
        self._turns = list(working)
        async for event in self._main_loop(user_input):
            yield event

    async def _main_loop(self, user_input: str, *, entry_notice: str | None = None) -> AsyncGenerator[AgentEvent]:
        """主循环（run 与 resume_run 共用）。"""
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
                system_prompt=self._system_prompt,
                user_input=user_input,
                working=self._turns,
                entry_notice=entry_notice,
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
            try:
                turn = await self._llm_step(messages)
            except (GatewayExhausted, GatewayOverloadedError) as exc:
                # §4.4 组一（闸门 #2 的 LLM 半边浮出面，C1）：deadline 耗尽/本地过载 = 步作废；
                # "降级分支"在 M2.7 定义为兜底话术 + 终止（03:49 未展开处的填补）
                cause = "gateway_exhausted" if isinstance(exc, GatewayExhausted) else "gateway_overloaded"
                await self._fail_llm_step(
                    TerminationReason.STEP_TIMEOUT,
                    cause=cause,
                    detail=str(exc),
                    fallback=FALLBACK_STEP_FAILED,
                )
                for event in self._events.drain():
                    yield event
                return
            except (BudgetExceeded, TenantQuotaExceeded) as exc:
                # §4.4 组二（D9）：三级预算共用终止原因，cause 区分层级（L2 预检不带 cause）
                cause = "l1_request_budget" if isinstance(exc, BudgetExceeded) else "l1_tenant_quota"
                await self._fail_llm_step(
                    TerminationReason.TOKEN_BUDGET_EXCEEDED,
                    cause=cause,
                    detail=str(exc),
                    fallback=FALLBACK_BUDGET,
                )
                for event in self._events.drain():
                    yield event
                return
            except GatewayRejected as exc:
                # C6：确定性拒绝 = 配置/协议 bug 信号——不发任何兜底话术（I9），
                # 不许被话术掩盖；detail 带错误文本（L1 已在源头打码）
                await self._fail_llm_step(
                    TerminationReason.GATEWAY_REJECTED,
                    cause="gateway_rejected",
                    detail=str(exc),
                    fallback=None,
                )
                for event in self._events.drain():
                    yield event
                return
            except GatewayStreamInterrupted as exc:
                # D10 作废重发：已收 chunk 全部丢弃（不入上下文、不计 token），配对 interrupted
                # 后 continue——重发消耗迭代数，max_iterations 天然兜底；进程死掉的半截归 M2.10。
                # 不接 GatewayError 基类：ProviderError 泄漏是 bug 信号，必须裸炸（§7 坑 5）
                await self._events.append(
                    EventType.LLM_RESULT,
                    {
                        "iteration": self._iteration,
                        "status": "interrupted",
                        "detail": f"{exc}；死因：{exc.__cause__!r}",
                    },
                )
                for event in self._events.drain():
                    yield event
                continue
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

    async def _run_tools(self, turn: _LLMTurn) -> TerminationReason | _Suspended | None:
        """工具分支（D20：顺序逐个执行，无并行）：闸门 #4/#6 检查点 + D6 幻觉记账 + 五结局回填。

        返回非 None = 已在内部 _terminate，run() 收尾外流后直接 return。
        执行器的业务结局全部编码在 ToolOutcome；基础设施异常（EventStoreUnavailable/
        EventWriteFenced）不在此捕获——裸穿出 run()（§4.4 末行：PG 挂=服务不可用，围栏=自毁）。
        """
        known = {spec.name for spec in self._tool_specs}
        total = len(turn.tool_calls)
        for index, call in enumerate(turn.tool_calls):
            # 闸门 #6：每个工具执行前的取消检查点（P1，与 LLM 调用前那次成对）
            if self._cancel_event is not None and self._cancel_event.is_set():
                await self._terminate(
                    TerminationReason.CANCELLED,
                    detail=_discard_note("收到取消信号（工具检查点）", total, index),
                    fallback=None,
                )
                return TerminationReason.CANCELLED

            # 闸门 #4 重复检测（D5 连续计数器）：key = (工具名, 参数规范形)，换 key 即重置
            key = (call.name, canonical_json(call.arguments_json))
            if key == self._repeat_key:
                self._repeat_streak += 1
            else:
                self._repeat_key = key
                self._repeat_streak = 1
            if self._repeat_streak > self._policy.repeat_call_limit:
                # 打断不清零，原样再犯 → 终止（03:51"再犯则终止"）
                await self._terminate(
                    TerminationReason.REPEATED_CALLS,
                    detail=_discard_note(f"打断后仍第 {self._repeat_streak} 次重复调用 {call.name}", total, index),
                    fallback=FALLBACK_REPEATED,
                )
                return TerminationReason.REPEATED_CALLS
            if self._repeat_streak == self._policy.repeat_call_limit:
                # 达阈值：该次不执行——无 write-ahead 即无 tool_call 事件（I8）；
                # 打断话术仍以 role=tool 配对回填，缺配对下一轮会被上游 400（§7 坑 8）
                self._feed_tool_message(call, PROMPT_REPEAT_BREAK.format(limit=self._policy.repeat_call_limit))
                continue

            # D6：幻觉工具名计入闸门 #5（语法是调用、语义非法）；回填文本用 executor 的
            # ERROR 话术（点名可用工具，executor.py:118-122），loop 只负责违规记账
            if call.name not in known:
                self._violations += 1
                if self._violations > self._policy.protocol_retry_limit:
                    await self._terminate(
                        TerminationReason.PROTOCOL_VIOLATION,
                        detail=_discard_note(f"幻觉工具名 {call.name}，连续违规第 {self._violations} 次", total, index),
                        fallback=FALLBACK_PROTOCOL,
                    )
                    return TerminationReason.PROTOCOL_VIOLATION

            outcome = await self._executor.execute(call.name, call.arguments_json)
            # M2.8 挂点②：五结局 content 一律包裹后回填（D5）——OK 含真实外部数据必须包；
            # ERROR/RESULT_UNKNOWN 可能转述下游异常文本，同样按不可信处理。
            # 事件 payload 已由 executor 存原文（X4），包裹只在 prompt 注入面
            wrapped = wrap_untrusted(outcome.content, source=f"tool:{outcome.tool_name}")
            if outcome.kind is OutcomeKind.NEEDS_APPROVAL:
                # M2.9 挂起链路（§4.3c）：开单（approvals 先于事件出生，store.py:273）→
                # approval_requested 事件 → T2 状态翻转 → 干净收尾（进程可下线）
                approval_id = uuid4().hex
                expires_at = datetime.now(UTC) + timedelta(seconds=self._policy.approval_ttl_s)
                args_snapshot: dict[str, Any] = json.loads(call.arguments_json)  # D6：LLM 原始参数快照
                await self._approvals.create(
                    approval_id=approval_id,
                    session_id=self._events.session_id,
                    tenant_id=self._tenant_id,
                    tool_name=outcome.tool_name,
                    args=args_snapshot,
                    expires_at=expires_at,
                )
                await self._events.append(
                    EventType.APPROVAL_REQUESTED,
                    {
                        "approval_id": approval_id,
                        "tool_name": outcome.tool_name,
                        "args": args_snapshot,
                        "expires_at": expires_at.isoformat(),  # datetime 不进 JSONB（坑 9）
                    },
                )
                flipped = await self._session_state.transition(
                    self._events.session_id, expected=RunState.RUNNING, to=RunState.AWAITING_APPROVAL
                )
                if not flipped:
                    raise RuntimeError(
                        f"会话 {self._events.session_id} 挂起时 T2 翻转失败——持锁单写者下不可能（bug 信号）"
                    )
                return _SUSPENDED
            # 其余四结局同样回填继续（§4.3 表）：错误文本是模型的观察结果，它通常能自我修正；
            # RESULT_UNKNOWN 的 content 已含"禁止重试"话术（X1），loop 不加工不终止
            self._feed_tool_message(call, wrapped)
        return None

    def _feed_tool_message(self, call: ToolCall, content: str) -> None:
        """工具/检索内容进工作序列的唯一入口（M2.8 挂点②：不可信数据包裹将挂这里）。

        tool_call_id 用模型侧 ToolCall.id（对话协议字段）——幂等键（事件 id）只进
        ToolContext 与事件流，两种 id 严禁混用（§7 坑 6）。
        """
        self._turns.append(Message(role="tool", content=content, tool_call_id=call.id))

    async def _finish_text(self, turn: _LLMTurn) -> None:
        """文本收尾单点（M2.8 挂点③）：出口守卫聚合检查 + 终局复检，然后才写 assistant_message。

        M2.7 实装为聚合后单发（08 §5.10）——OutputGuard 确定性不变量（逐字符 ≡ 整段）
        保证聚合 feed 与 M3.10 逐帧 feed 行为一致；_llm_step 消费结构零改动（流中
        提前退出会丢 ToolCallChunk/UsageChunk，工具轮误判 + 计量蒸发）。
        """
        guard = self._guards.output_guard(
            # 片段集用 spec 原文：UNTRUSTED_NOTICE 是公开机制说明，模型复述无害不设防
            system_prompt=self._spec.system_prompt,
            tool_names=[spec.name for spec in self._tool_specs],
            owned_values=self._spec.owned_values,
        )
        visible = guard.feed(turn.text) + guard.flush()
        if guard.hit is not None:
            # 流中命中（D11 止损）：已放行前缀 + 安全话术，命中句起全部丢弃
            await self._events.append(EventType.GUARDRAIL_TRIGGERED, output_audit_payload(guard.hit, stage="stream"))
            await self._events.append(
                EventType.ASSISTANT_MESSAGE,
                {"content": visible + SAFE_REPLY, "guardrail_truncated": True, "token_usage": turn.usage_completion},
            )
            return
        final_hits = guard.final_check(visible)
        if final_hits:
            # 终局命中：M2 时点 assistant_message 尚未写出，可整条替换（D11）
            await self._events.append(EventType.GUARDRAIL_TRIGGERED, output_audit_payload(final_hits[0], stage="final"))
            await self._events.append(
                EventType.ASSISTANT_MESSAGE,
                {"content": SAFE_REPLY, "guardrail_truncated": True, "token_usage": turn.usage_completion},
            )
            return
        await self._events.append(
            EventType.ASSISTANT_MESSAGE,
            {"content": turn.text, "token_usage": turn.usage_completion},
        )

    async def _fail_llm_step(
        self,
        reason: TerminationReason,
        *,
        cause: str,
        detail: str,
        fallback: str | None,
    ) -> None:
        """§4.4 终止型异常的统一收尾：先配对 llm_result(failed)——I6 在进程内不留孤儿
        llm_call，"有 call 无 result"留给真崩溃（M2.10 判据）——再走 _terminate；
        cause 随 llm_result 与 loop_terminated 两处留痕。"""
        await self._events.append(
            EventType.LLM_RESULT,
            {"iteration": self._iteration, "status": "failed", "cause": cause, "detail": detail},
        )
        await self._terminate(reason, detail=detail, fallback=fallback, cause=cause)

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
        # T4（M2.9/D20）：终止即归位 idle。持锁单写者下失败=状态机被旁路——响亮留痕不掀收尾
        if not await self._session_state.transition(
            self._events.session_id, expected=RunState.RUNNING, to=RunState.IDLE
        ):
            logger.warning("终止时 running→idle 翻转失败：session=%s", self._events.session_id)

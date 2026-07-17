"""AgentRuntime 门面与 GatewayLike 协议（03 §1/§7；M2.7 接电，M2.9 接锁与恢复单入口）。

命名分工（03 §1）：AgentRuntime 对外门面；AgentLoop 内部驱动，对 L3 不可见。
M2.9 新增：run() 先取会话锁（store.py:288 单写者前提接电）；resume() 恢复单入口
（"先取会话锁再恢复"，批准/拒绝/撤回/超时四结局统一分诊）；PrecheckHook 挂点
（M3.9 注入业务校验）。lock=None = 无锁直通（M2 测试形态；2026-07-17 拍板：
get_redis()/get_engine() 进程单例跨 event loop 不可复用）——M3.2 API 层组装时
必须显式传 build_session_lock()。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import aclosing, asynccontextmanager, suppress
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import select

from aegis.core.config import Settings, get_settings
from aegis.core.locks import SessionLock, SessionLockHeld, hold_session_lock
from aegis.gateway.schema import LLMChunk, LLMRequest, Message, TextDelta, ToolCall
from aegis.runtime.context import ContextBuilder
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.executor import ToolExecutor
from aegis.runtime.guardrails import Classifier, Guardrails, build_classifier, wrap_untrusted
from aegis.runtime.loop import AgentLoop, _Tap
from aegis.runtime.spec import AgentSpec, TerminationReason
from aegis.runtime.store import (
    ApprovalRecord,
    ApprovalStatus,
    ApprovalStore,
    EventRecord,
    EventWriter,
    LeaseLost,
    LeaseStore,
    RunState,
    SessionFactory,
    SessionRecord,
    SessionStateStore,
    default_lease_owner,
)
from aegis.runtime.tools import ToolRegistry

logger = logging.getLogger(__name__)


class GatewayLike(Protocol):
    """L2 眼中的网关（03 §7）。def 不是 async def：调用即得 AsyncGenerator。

    异常契约：只允许 00 §2.2 三组六类穿出，ProviderError 家族永不出网关。
    """

    def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]: ...


PrecheckHook = Callable[[str, Mapping[str, Any]], Awaitable[str | None]]
"""批准后前置校验挂点（00 §10.1 #8）：(tool_name, args 快照) -> None=通过 / str=拒绝原因。
校验逻辑（订单状态/可退余额）M3.9 注入；M2 默认 None=全通过。"""


_SUMMARIZE_PROMPT = (
    "请将下面的客服对话内容压缩为要点摘要：保留订单号、金额、时间、用户诉求与已确认的结论，"
    "省略寒暄与重复；只输出摘要正文。"
)
"""摘要指令（D13 唯一例外：随唯一消费者 _make_summarizer 落本模块）。
参与 summary/tool_digest 两道的 cassette 匹配语义——改动会让重录 diff 扩散，定了不动。"""

_DISCARDED_NOTE = "该调用在等待人工审批期间未执行；如仍需要请重新发起。"
_PRECHECK_VETO_TEMPLATE = "审批已通过但前置校验未过：{reason}，操作未执行。"


def _make_summarizer(view: GatewayLike, tenant_id: str, session_id: str) -> Callable[[str], Awaitable[str]]:
    """从网关视图构造摘要钩子（D15）：ToolExecutor 与 ContextBuilder 的 summarize 同源于此。"""

    async def summarize(text: str) -> str:
        request = LLMRequest(
            tier="fast",
            messages=[Message(role="user", content=f"{_SUMMARIZE_PROMPT}\n\n{text}")],
            tenant_id=tenant_id,
            session_id=session_id,
        )
        parts: list[str] = []
        stream = view.complete(request)
        async with aclosing(stream):
            async for chunk in stream:
                if isinstance(chunk, TextDelta):
                    parts.append(chunk.text)
        return "".join(parts)

    return summarize


@asynccontextmanager
async def _maybe_lock(lock: SessionLock | None, session_id: str) -> AsyncIterator[None]:
    """锁的条件持有：None=无锁直通（M2 测试形态）；非 None 走 hold_session_lock 看门狗形态。"""
    if lock is None:
        yield None
    else:
        async with hold_session_lock(lock, session_id):
            yield None


async def _renew_lease_forever(
    leases: LeaseStore,
    session_id: str,
    *,
    owner: str,
    generation: int,
    ttl_s: float,
    interval_s: float,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """续租心跳（C2 协议一）：打空即抛 LeaseLost——终态不重试（协议二），自毁由消费方执行。"""
    while True:
        await sleep(interval_s)
        if not await leases.renew(session_id, owner=owner, generation=generation, ttl_s=ttl_s):
            raise LeaseLost(f"session={session_id} gen={generation} 续租打空——所有权已旁落")


def _match_call(pending: Sequence[ToolCall], matched: list[bool], name: str, args: Mapping[str, Any]) -> int | None:
    """按 (工具名, 参数语义) 在未配对的声明里找调用——模型侧 id 不落工具事件，语义配对是唯一通路。"""
    for i, call in enumerate(pending):
        if matched[i] or call.name != name:
            continue
        try:
            if json.loads(call.arguments_json) == dict(args):
                return i
        except json.JSONDecodeError:
            continue
    return None


def _rebuild_working(
    records: Sequence[tuple[str, Mapping[str, Any]]],
    *,
    fill_name: str | None = None,
    fill_args: Mapping[str, Any] | None = None,
    fill_content: str | None = None,
) -> list[Message]:
    """K2② 定案：从挂起 run 的事件流重建工作消息序列（模型视界的事实级还原）。

    llm_result(ok) 工具轮 → assistant(tool_calls) 协议消息（模型侧 id 在事件里）；
    tool_call（write-ahead）暂存 (name, args)，随后的 tool_result/tool_error 据此配对——
    content 优先取 injected（X4 收缩产物留痕正为回放重建），否则 dumps(result) 与
    executor 同参逐字节一致；tool_error 近似还原（事件存短错误文本，包装前缀不落盘）。
    fill_*（m2.10 偏差 #6 泛化）：给指定未配对 call 喂结果内容——审批场景喂批准执行
    结果、崩溃恢复悬挂工具支喂 reexecute 结果；无 fill 目标（悬挂 LLM/干净缝）传 None。
    其余未配对（弃置/打断）补话术防悬空 tool_calls 被上游 400。
    全部 tool 消息重过 wrap_untrusted（确定性函数，与挂起前 loop 行为一致——M2.8 挂点②）。
    已知边界（m2.9 偏差 #1）：打断/纠错话术无事件不重建——恢复保事实不保字节。
    """
    working: list[Message] = []
    pending: list[ToolCall] = []
    matched: list[bool] = []
    last_exec: tuple[str, Mapping[str, Any]] | None = None

    def _feed(index: int, content: str) -> None:
        matched[index] = True
        call = pending[index]
        working.append(
            Message(
                role="tool",
                content=wrap_untrusted(content, source=f"tool:{call.name}"),
                tool_call_id=call.id,
            )
        )

    for etype, payload in records:
        if etype == EventType.LLM_RESULT.value and payload.get("status") == "ok" and payload.get("tool_calls"):
            calls = [
                ToolCall(id=c["id"], name=c["name"], arguments_json=c["arguments_json"]) for c in payload["tool_calls"]
            ]
            working.append(Message(role="assistant", content=payload.get("text", ""), tool_calls=calls))
            pending, matched, last_exec = calls, [False] * len(calls), None
        elif etype == EventType.TOOL_CALL.value:
            last_exec = (payload["tool_name"], payload["args"])
        elif etype == EventType.TOOL_RESULT.value and last_exec is not None:
            content = payload.get("injected") or json.dumps(payload["result"], ensure_ascii=False, default=str)
            index = _match_call(pending, matched, *last_exec)
            if index is not None:
                _feed(index, content)
            last_exec = None
        elif etype == EventType.TOOL_ERROR.value and last_exec is not None:
            index = _match_call(pending, matched, *last_exec)
            if index is not None:
                _feed(index, f"工具执行失败：{payload['error']}")
            last_exec = None

    if fill_name is not None and fill_args is not None and fill_content is not None:
        index = _match_call(pending, matched, fill_name, fill_args)
        if index is not None:
            _feed(index, fill_content)
    for i in range(len(pending)):
        if not matched[i]:
            _feed(i, _DISCARDED_NOTE)
    return working


class AgentRuntime:
    """对外门面：一次 run = 一条事件流。M2.9 起 run/resume 都在会话锁内执行。"""

    def __init__(
        self,
        gateway: GatewayLike,
        session_factory: SessionFactory,
        *,
        cancel_event: asyncio.Event | None = None,
        run_id_factory: Callable[[], str] | None = None,
        lock: SessionLock | None = None,
        precheck: PrecheckHook | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._gateway = gateway
        self._session_factory = session_factory
        self._cancel_event = cancel_event
        self._run_id_factory = run_id_factory or (lambda: uuid4().hex)
        self._lock = lock  # None=无锁直通；M3.2 必须显式传 build_session_lock()
        self._precheck = precheck
        self._settings = settings or get_settings()  # 测试注入小值实例（config.py:72 指引，绕 lru_cache）
        self._session_state = SessionStateStore(session_factory)
        self._approvals = ApprovalStore(session_factory)
        self._leases = LeaseStore(session_factory)
        self._lease_owner = default_lease_owner()

    async def run(self, spec: AgentSpec, session_id: str, user_input: str) -> AsyncIterator[AgentEvent]:
        """驱动一次完整 Agent 循环。本签名是 M2 的对外契约，定死不再动。"""
        async with _maybe_lock(self._lock, session_id):
            async for event in self._run_locked(spec, session_id, user_input):
                yield event

    async def resume(
        self, spec: AgentSpec, session_id: str, approval_id: str | None = None
    ) -> AsyncIterator[AgentEvent]:
        """恢复单入口："先取会话锁再恢复"（03 §5）。四种审批结局统一分诊。

        approval_id 形参即 M2.10 泛化后的最终形：非 None=审批分诊（本步实装）；
        None=崩溃恢复分诊（M2.10 接入，暂 NotImplementedError 占位）。
        """
        async with _maybe_lock(self._lock, session_id):
            if approval_id is None:
                async for event in self._recover_locked(spec, session_id):
                    yield event
            else:
                async for event in self._resume_locked(spec, session_id, approval_id):
                    yield event

    async def _identity_and_seed(self, session_id: str) -> tuple[str, str, int]:
        """读 sessions 行取身份（P2：无行拒绝起跑）+ 从事件流重建 token 计数种子（D8）。"""
        async with self._session_factory() as s:
            identity = (
                await s.execute(
                    select(SessionRecord.tenant_id, SessionRecord.user_id).where(SessionRecord.id == session_id)
                )
            ).one_or_none()
            if identity is None:
                raise ValueError(f"会话 {session_id} 不存在——run 之前必须先建 sessions 行（P2）")
            payloads = (
                (
                    await s.execute(
                        select(EventRecord.payload).where(
                            EventRecord.session_id == session_id,
                            EventRecord.type.in_((EventType.LLM_CALL.value, EventType.LLM_RESULT.value)),
                        )
                    )
                )
                .scalars()
                .all()
            )
        token_seed = sum(p.get("input_tokens_est", 0) + p.get("output_tokens_est", 0) for p in payloads)
        return identity[0], identity[1], token_seed

    def _assemble(
        self, spec: AgentSpec, tap: _Tap, *, tenant_id: str, user_id: str, session_id: str, token_seed: int
    ) -> tuple[AgentLoop, ToolExecutor]:
        """组装（run 与 resume 共用）：registry/executor/builder/guards/loop 一次备齐。"""
        from aegis.runtime.replay import scoped_view  # 延迟 import 破环（replay 顶层引用本模块）

        registry = ToolRegistry(spec.tools)
        executor = ToolExecutor(
            registry,
            tap,
            tenant_id=tenant_id,
            user_id=user_id,
            tenant_config=spec.tenant_config,
            default_timeout_s=spec.policy.tool_step_timeout_s,
            result_token_budget=spec.context_config.tool_results_budget,
            summarize=_make_summarizer(scoped_view(self._gateway, "tool_digest"), tenant_id, session_id),
        )
        builder = ContextBuilder(
            self._session_factory,
            tap,
            config=spec.context_config,
            tenant_id=tenant_id,
            user_id=user_id,
            summarize=_make_summarizer(scoped_view(self._gateway, "summary"), tenant_id, session_id),
        )
        classify: Classifier | None = None
        if spec.entry_classifier:
            classify = build_classifier(scoped_view(self._gateway, "guard"), tenant_id=tenant_id, session_id=session_id)
        loop = AgentLoop(
            spec,
            scoped_view(self._gateway, "main"),
            tap,
            builder,
            executor,
            tenant_id=tenant_id,
            token_seed=token_seed,
            cancel_event=self._cancel_event,
            guards=Guardrails(classify=classify),
            approvals=self._approvals,
            session_state=self._session_state,
        )
        return loop, executor

    async def _run_locked(self, spec: AgentSpec, session_id: str, user_input: str) -> AsyncIterator[AgentEvent]:
        run_id = self._run_id_factory()
        tenant_id, user_id, token_seed = await self._identity_and_seed(session_id)
        # T1（M2.9/D20）：循环启动前 idle→running；失败=会话在挂起/运行中——
        # M2 时点 fail-loud，M3.2 消息准入层将按 run_state 映射业务提示
        if not await self._session_state.transition(session_id, expected=RunState.IDLE, to=RunState.RUNNING):
            raise RuntimeError(f"会话 {session_id} 不在 idle（等待审批或运行中），本次 run 拒绝启动")
        generation = await self._leases.acquire(session_id, owner=self._lease_owner, ttl_s=self._settings.lease_ttl_s)
        if generation is None:
            # T1 赢了但租约在他人手里 = 异常态；不回滚状态（running+无租约的幽灵由
            # reaper 的 NULL 扫描兜住，m2.10 偏差 #5），按锁被占同款信号退出
            raise SessionLockHeld(f"会话 {session_id} 的租约在另一副本手里")
        writer = await EventWriter.open(self._session_factory, session_id, run_id)
        tap = _Tap(writer)
        loop, _ = self._assemble(
            spec, tap, tenant_id=tenant_id, user_id=user_id, session_id=session_id, token_seed=token_seed
        )
        async for event in self._pump_with_lease(session_id, generation, loop.run(user_input)):
            yield event

    async def _pump_with_lease(
        self, session_id: str, generation: int, events: AsyncGenerator[AgentEvent]
    ) -> AsyncIterator[AgentEvent]:
        """租约伴飞：续租任务后台跑，事件间检查其死活；正常耗尽才 release。

        续租打空 → LeaseLost 从此处抛出，立即停止消费源生成器（aclosing 关它，
        不再写任何事件——含 loop_terminated：新 owner 已在接续 seq，再写必撞唯一约束）；
        异常路径不 release（所有权已旁落，围栏终态 C2）。
        """
        renew = asyncio.create_task(
            _renew_lease_forever(
                self._leases,
                session_id,
                owner=self._lease_owner,
                generation=generation,
                ttl_s=self._settings.lease_ttl_s,
                interval_s=self._settings.lease_renew_interval_s,
            )
        )
        try:
            async with aclosing(events):
                async for event in events:
                    if renew.done():
                        renew.result()  # 心跳只以异常终结：此处必抛 LeaseLost
                    yield event
        finally:
            renew.cancel()
            with suppress(asyncio.CancelledError):
                await renew
        if not await self._leases.release(session_id, owner=self._lease_owner, generation=generation):
            logger.warning(
                "release 打空：session=%s gen=%s（租约已旁落，事件与置位已由前序完成）", session_id, generation
            )

    async def _recover_locked(self, spec: AgentSpec, session_id: str) -> AsyncIterator[AgentEvent]:
        """崩溃恢复分诊（m2.10 §4.4，approval_id=None 分支）：读事实 → 四支判定 → 续跑。

        前提：调用方已发现该会话租约过期（reaper steal 后经钩子进来，或人工触发）。
        四支（按序最多命中一支）：
        a. 尾事件 loop_terminated —— 上一 run 已收尾只是 T4 没置回：仅修状态，零新事件；
        b. 悬挂 tool_call（有 write-ahead 无终局）—— executor.reexecute 凭原事件 id 重执行
           （恰一把幂等键），结果经 fill 配对进重建序列续跑；
        c. 悬挂 llm_call（I6：无任何 llm_result 配对）—— 作废重发：不补旧事件，
           续跑自然产生新 llm_call（显式接受重生成文本不同，03:149-151）；
        d. 干净缝 —— 直接续跑。
        """
        generation = await self._leases.acquire(session_id, owner=self._lease_owner, ttl_s=self._settings.lease_ttl_s)
        if generation is None:
            raise SessionLockHeld(f"会话 {session_id} 的租约在另一副本手里")
        async with self._session_factory() as s:
            rows = (
                await s.execute(
                    select(
                        EventRecord.id,
                        EventRecord.run_id,
                        EventRecord.type,
                        EventRecord.payload,
                        EventRecord.schema_version,
                    )
                    .where(EventRecord.session_id == session_id)
                    .order_by(EventRecord.seq)
                )
            ).all()
        if not rows:
            raise ValueError(f"会话 {session_id} 无任何事件——没有可恢复的 run")
        for r in rows:
            if r.schema_version != 1:
                raise RuntimeError(f"事件 schema_version={r.schema_version} 无解析器（当前仅 v1）")

        # a 支：上一 run 其实已收尾——仅修状态（T4 补翻 + 清租约），零新事件
        if rows[-1].type == EventType.LOOP_TERMINATED.value:
            if not await self._session_state.transition(session_id, expected=RunState.RUNNING, to=RunState.IDLE):
                logger.warning("崩溃修状态：running→idle 翻转失败（可能已被处理）：session=%s", session_id)
            if not await self._leases.release(session_id, owner=self._lease_owner, generation=generation):
                logger.warning("崩溃修状态：release 打空：session=%s", session_id)
            return

        # 扫描配对（全会话）：悬挂 tool_call 判定（K2/I6）。半截 llm_call（c 支）不必显式
        # 判定——它与干净缝（d 支）的处置相同：都不补事件、直接续跑（作废重发的"作废"
        # 就是无为，重发由续跑的新 llm_call 自然兑现），两支在代码上合流
        open_calls: dict[str, Mapping[str, Any]] = {}
        for r in rows:
            if r.type == EventType.TOOL_CALL.value:
                open_calls[r.id] = r.payload
            elif r.type in (EventType.TOOL_RESULT.value, EventType.TOOL_ERROR.value):
                open_calls.pop(r.payload.get("tool_call_id", ""), None)
        if len(open_calls) > 1:
            raise RuntimeError(
                f"会话 {session_id} 悬挂 tool_call 多于一个（{len(open_calls)}）——单写者顺序执行下不可能"
            )

        crash_run_id = rows[-1].run_id
        crash_rows = [(r.type, r.payload) for r in rows if r.run_id == crash_run_id]
        user_input = next((r.payload["content"] for r in reversed(rows) if r.type == EventType.USER_MESSAGE.value), "")
        tenant_id, user_id, token_seed = await self._identity_and_seed(session_id)
        run_id = self._run_id_factory()  # 恢复用新 run_id（X5），seq 接续旧流
        writer = await EventWriter.open(self._session_factory, session_id, run_id)
        tap = _Tap(writer)
        loop, executor = self._assemble(
            spec, tap, tenant_id=tenant_id, user_id=user_id, session_id=session_id, token_seed=token_seed
        )

        fill_name: str | None = None
        fill_args: Mapping[str, Any] | None = None
        fill_content: str | None = None
        if open_calls:
            # b 支：凭原事件 id 重执行（reexecute 以原 id 写终局，投影闭合原 RUNNING 行）
            call_event_id, call_payload = next(iter(open_calls.items()))
            outcome = await executor.reexecute(
                call_payload["tool_name"], call_payload["args"], tool_call_id=call_event_id
            )
            fill_name = call_payload["tool_name"]
            fill_args = call_payload["args"]
            fill_content = outcome.content
        # c 支（悬挂 llm_call：last_llm_call > last_llm_result）与 d 支（干净缝）都不补事件，
        # 区别仅在语义：c 的旧调用被作废（重发消耗新 llm_call），d 本来就没有半截
        for event in tap.drain():
            yield event
        working = _rebuild_working(crash_rows, fill_name=fill_name, fill_args=fill_args, fill_content=fill_content)
        async for event in self._pump_with_lease(session_id, generation, loop.resume_run(user_input, working)):
            yield event

    async def _load_suspension(
        self, session_id: str, approval_id: str
    ) -> tuple[str, str, Mapping[str, Any], list[tuple[str, Mapping[str, Any]]]]:
        """定位挂起 run 并取其事件序列：返回 (user_input, 审批工具名, 审批参数, 该 run 全事件)。"""
        async with self._session_factory() as s:
            rows = (
                await s.execute(
                    select(EventRecord.run_id, EventRecord.type, EventRecord.payload)
                    .where(EventRecord.session_id == session_id)
                    .order_by(EventRecord.seq)
                )
            ).all()
        suspend_run_id = next(
            r.run_id
            for r in rows
            if r.type == EventType.APPROVAL_REQUESTED.value and r.payload.get("approval_id") == approval_id
        )
        run_rows = [(r.type, r.payload) for r in rows if r.run_id == suspend_run_id]
        user_input = next(p["content"] for t, p in run_rows if t == EventType.USER_MESSAGE.value)
        req = next(
            p for t, p in run_rows if t == EventType.APPROVAL_REQUESTED.value and p.get("approval_id") == approval_id
        )
        return user_input, req["tool_name"], req["args"], run_rows

    async def _resume_locked(self, spec: AgentSpec, session_id: str, approval_id: str) -> AsyncIterator[AgentEvent]:
        async with self._session_factory() as s:
            approval = (
                await s.execute(select(ApprovalRecord).where(ApprovalRecord.id == approval_id))
            ).scalar_one_or_none()
        if approval is None or approval.session_id != session_id:
            raise ValueError(f"审批单 {approval_id} 不存在或不属于会话 {session_id}")
        if approval.status == ApprovalStatus.PENDING.value:
            raise ValueError(f"审批单 {approval_id} 仍是 pending——先 decide/cancel/expire_due 再 resume（D21）")
        # T3：四种结局统一先回 running（D3）；CAS 失败=并发赢家已处理（双击第二击）→ 安静零事件
        if not await self._session_state.transition(
            session_id, expected=RunState.AWAITING_APPROVAL, to=RunState.RUNNING
        ):
            return
        generation = await self._leases.acquire(session_id, owner=self._lease_owner, ttl_s=self._settings.lease_ttl_s)
        if generation is None:
            raise SessionLockHeld(f"会话 {session_id} 的租约在另一副本手里")
        run_id = self._run_id_factory()  # 恢复用新 run_id（D16/X5），seq 经 open 接续旧流
        writer = await EventWriter.open(self._session_factory, session_id, run_id)
        tap = _Tap(writer)

        if approval.status == ApprovalStatus.APPROVED.value:
            tenant_id, user_id, token_seed = await self._identity_and_seed(session_id)
            loop, executor = self._assemble(
                spec, tap, tenant_id=tenant_id, user_id=user_id, session_id=session_id, token_seed=token_seed
            )
            await tap.append(
                EventType.APPROVAL_DECIDED,
                {"approval_id": approval_id, "approved": True, "operator_id": approval.operator_id},
            )
            args: Mapping[str, Any] = approval.args
            veto = None if self._precheck is None else await self._precheck(approval.tool_name, args)
            if veto is not None:
                # D19：否决不终止——工具不执行（无 write-ahead），原因作为观察结果回填模型
                approved_content = _PRECHECK_VETO_TEMPLATE.format(reason=veto)
            else:
                outcome = await executor.execute(
                    approval.tool_name, json.dumps(dict(args), ensure_ascii=False), approved=True
                )
                approved_content = outcome.content
                if outcome.tool_call_id is not None:
                    await self._approvals.attach_event(approval_id, event_id=outcome.tool_call_id)
            for event in tap.drain():
                yield event
            user_input, approved_name, approved_args, run_rows = await self._load_suspension(session_id, approval_id)
            working = _rebuild_working(
                run_rows, fill_name=approved_name, fill_args=approved_args, fill_content=approved_content
            )
            async for event in self._pump_with_lease(session_id, generation, loop.resume_run(user_input, working)):
                yield event
            return

        # 拒绝/撤回/过期：对应事件 → cancelled 终止（闸门 #6）→ T4 归位（轻量路径，不组装 loop）
        if approval.status == ApprovalStatus.REJECTED.value:
            await tap.append(
                EventType.APPROVAL_DECIDED,
                {"approval_id": approval_id, "approved": False, "operator_id": approval.operator_id},
            )
            detail = f"审批被拒绝：approval_id={approval_id}"
        elif approval.status == ApprovalStatus.CANCELLED.value:
            await tap.append(EventType.APPROVAL_CANCELLED, {"approval_id": approval_id})
            detail = f"审批被撤回：approval_id={approval_id}"
        else:
            await tap.append(EventType.APPROVAL_EXPIRED, {"approval_id": approval_id})
            detail = f"审批超时：approval_id={approval_id}"
        await tap.append(
            EventType.LOOP_TERMINATED,
            {"reason": TerminationReason.CANCELLED.value, "iteration": 0, "detail": detail},
        )
        if not await self._session_state.transition(session_id, expected=RunState.RUNNING, to=RunState.IDLE):
            logger.warning("恢复终止时 running→idle 翻转失败：session=%s", session_id)
        if not await self._leases.release(session_id, owner=self._lease_owner, generation=generation):
            logger.warning("拒绝路径 release 打空：session=%s", session_id)
        for event in tap.drain():
            yield event

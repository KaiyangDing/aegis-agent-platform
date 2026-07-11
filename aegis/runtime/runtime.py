"""AgentRuntime 门面与 GatewayLike 协议（03 §1/§7，M2.1 交付③；M2.7 总装接电）。

命名分工（03 §1 原话："两个名字各指其一，不是同义漂移"）：
- AgentRuntime：对外门面，L3 只认识它——构造时注入网关，run() 驱动一次
  完整循环、以事件流产出全部中间步骤；
- AgentLoop（loop.py，M2.7）：内部驱动，持会话锁的单写者，管七类终止、
  上下文组装与工具执行的编排——对 L3 不可见。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select

from aegis.gateway.schema import LLMChunk, LLMRequest, Message, TextDelta
from aegis.runtime.context import ContextBuilder
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.executor import ToolExecutor
from aegis.runtime.loop import AgentLoop, _Tap
from aegis.runtime.spec import AgentSpec
from aegis.runtime.store import EventRecord, EventWriter, SessionFactory, SessionRecord
from aegis.runtime.tools import ToolRegistry


class GatewayLike(Protocol):
    """L2 眼中的网关（03 §7 的 LLMGateway Protocol；代码名沿用仓库 *Like 惯例）。

    结构化协议：gateway.router.LLMGateway 天然满足，M2.6 的 FakeGateway 也只需
    长出这一个方法——录制回放的可替换性由此而来。
    注意是 def 不是 async def：async 生成器方法的类型是"调用后返回
    AsyncGenerator"，与 providers/base.py 的 Provider 协议同款。
    异常契约：只允许 00 §2.2 三组六类穿出，ProviderError 家族永不出网关。
    """

    def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]: ...


_SUMMARIZE_PROMPT = (
    "请将下面的客服对话内容压缩为要点摘要：保留订单号、金额、时间、用户诉求与已确认的结论，"
    "省略寒暄与重复；只输出摘要正文。"
)
"""摘要指令（D13 唯一例外：随唯一消费者 _make_summarizer 落本模块）。
参与 summary/tool_digest 两道的 cassette 匹配语义——改动会让重录 diff 扩散，定了不动。"""


def _make_summarizer(view: GatewayLike, tenant_id: str, session_id: str) -> Callable[[str], Awaitable[str]]:
    """从网关视图构造摘要钩子（D15）：ToolExecutor 与 ContextBuilder 的 summarize 同源于此。

    fast 档小额辅助调用；deadline_s 不设——L1 首块 25s/空闲 30s 已兜底（C1 不做人肉算术）；
    失败不在这里兜底：executor（硬截断）与 builder（丢轮）各有 C34 fail-open 路径。
    """

    async def summarize(text: str) -> str:
        request = LLMRequest(
            tier="fast",
            messages=[Message(role="user", content=f"{_SUMMARIZE_PROMPT}\n\n{text}")],
            tenant_id=tenant_id,
            session_id=session_id,  # 回放按 (session_id, scope, 道内序号) 匹配——必带
        )
        parts: list[str] = []
        stream = view.complete(request)
        async with aclosing(stream):
            async for chunk in stream:
                if isinstance(chunk, TextDelta):
                    parts.append(chunk.text)
        return "".join(parts)

    return summarize


class AgentRuntime:
    """对外门面：一次 run = 一条事件流。M2.7 接电——只做组装与委托，编排逻辑全在 AgentLoop。"""

    def __init__(
        self,
        gateway: GatewayLike,
        session_factory: SessionFactory,
        *,
        cancel_event: asyncio.Event | None = None,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._gateway = gateway
        self._session_factory = session_factory  # 按形状注入（store.py:168-170）：测试故障工厂由此进来
        self._cancel_event = cancel_event  # P1 拍板：None=永不取消；M2.9/M3.2 真实触发源 set 同一事件
        self._run_id_factory = run_id_factory or (lambda: uuid4().hex)

    async def run(self, spec: AgentSpec, session_id: str, user_input: str) -> AsyncIterator[AgentEvent]:
        """驱动一次完整 Agent 循环，事件流形式产出所有中间步骤（03 §1）。

        本签名是 M2 的对外契约，定死不再动。
        """
        # 延迟 import 破环：replay 模块级引用本模块的 GatewayLike（replay.py:24），
        # 顶层互相 import 会在模块初始化半途炸 ImportError
        from aegis.runtime.replay import scoped_view

        run_id = self._run_id_factory()  # X5：run_id 每次启动新生成
        async with self._session_factory() as s:
            # P2 拍板：身份跟会话走——读 sessions 行取 tenant/user（M2 测试自建行，M3.2 归 API 层）
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
        tenant_id, user_id = identity
        # D8 会话级口径：预算计数种子从事件流重建（事件即事实源，不加新列、不新增查询面）
        token_seed = sum(p.get("input_tokens_est", 0) + p.get("output_tokens_est", 0) for p in payloads)

        # M2.9 将在此之前插入"先取会话锁"——EventWriter 单写者前提的接电位（store.py:288）
        writer = await EventWriter.open(self._session_factory, session_id, run_id)
        tap = _Tap(writer)
        registry = ToolRegistry(spec.tools)
        executor = ToolExecutor(
            registry,
            tap,
            tenant_id=tenant_id,
            user_id=user_id,
            tenant_config=spec.tenant_config,
            # I3 显式接线（08 §8 #10）：此前靠默认值巧合相等（30.0/3_000），从此改 policy 必须生效
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
            # D15②：滚动摘要钩子显式接线——漏接则 summarize=None、摘要永不触发（M2.11 必挂）
            summarize=_make_summarizer(scoped_view(self._gateway, "summary"), tenant_id, session_id),
        )
        loop = AgentLoop(
            spec,
            scoped_view(self._gateway, "main"),
            tap,
            builder,
            executor,
            tenant_id=tenant_id,
            token_seed=token_seed,
            cancel_event=self._cancel_event,
        )
        async for event in loop.run(user_input):
            yield event

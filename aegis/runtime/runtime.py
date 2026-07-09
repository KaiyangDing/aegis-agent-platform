"""AgentRuntime 门面与 GatewayLike 协议（03 §1/§7，M2.1 交付③）。

命名分工（03 §1 原话："两个名字各指其一，不是同义漂移"）：
- AgentRuntime：对外门面，L3 只认识它——构造时注入网关，run() 驱动一次
  完整循环、以事件流产出全部中间步骤；
- AgentLoop（loop.py，M2.7）：内部驱动，持会话锁的单写者，管七类终止、
  上下文组装与工具执行的编排——对 L3 不可见。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from typing import Protocol

from aegis.gateway.schema import LLMChunk, LLMRequest
from aegis.runtime.events import AgentEvent
from aegis.runtime.spec import AgentSpec


class GatewayLike(Protocol):
    """L2 眼中的网关（03 §7 的 LLMGateway Protocol；代码名沿用仓库 *Like 惯例）。

    结构化协议：gateway.router.LLMGateway 天然满足，M2.6 的 FakeGateway 也只需
    长出这一个方法——录制回放的可替换性由此而来。
    注意是 def 不是 async def：async 生成器方法的类型是"调用后返回
    AsyncGenerator"，与 providers/base.py 的 Provider 协议同款。
    异常契约：只允许 00 §2.2 三组六类穿出，ProviderError 家族永不出网关。
    """

    def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]: ...


class AgentRuntime:
    """对外门面：一次 run = 一条事件流。循环体随 M2.7 总装接电。"""

    def __init__(self, gateway: GatewayLike) -> None:
        self._gateway = gateway

    async def run(self, spec: AgentSpec, session_id: str, user_input: str) -> AsyncIterator[AgentEvent]:
        """驱动一次完整 Agent 循环，事件流形式产出所有中间步骤（03 §1）。

        本签名是 M2 的对外契约，本步定死不再动。
        """
        raise NotImplementedError("AgentLoop 随 M2.7 总装交付")
        yield  # 不可达；让本函数成为 async 生成器（无 yield 则调用语义完全不同）

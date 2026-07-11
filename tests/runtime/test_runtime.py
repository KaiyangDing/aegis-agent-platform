"""M2.1 交付③（M2.7 改写）：门面契约测试——run 签名快照 + 真网关协议兼容。

M2.7 前此处断言 NotImplementedError（循环未接电）；接电后改为签名锁：
run() 是 M2 的对外契约（runtime.py），参数名与注解逐项钉死，动它先让这里红。
行为测试全在 test_loop_*.py，本文件只守契约形状。
"""

from __future__ import annotations

import inspect

from aegis.gateway.router import LLMGateway as RouterGateway
from aegis.runtime.runtime import AgentRuntime, GatewayLike


def test_real_gateway_structurally_satisfies_protocol() -> None:
    """兼容性由 mypy 静态验证：内层函数永不执行，真网关签名若漂移，mypy 先红。"""

    def _accepts(g: GatewayLike) -> None: ...

    def _feed(real: RouterGateway) -> None:
        _accepts(real)

    assert True


def test_run_signature_unchanged() -> None:
    """签名快照（全仓开 future annotations，注解在运行时是字符串——按字符串断言）。"""
    sig = inspect.signature(AgentRuntime.run)
    assert list(sig.parameters) == ["self", "spec", "session_id", "user_input"]
    assert sig.parameters["spec"].annotation == "AgentSpec"
    assert sig.parameters["session_id"].annotation == "str"
    assert sig.parameters["user_input"].annotation == "str"
    assert sig.return_annotation == "AsyncIterator[AgentEvent]"

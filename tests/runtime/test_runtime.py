"""M2.1 交付③：门面契约测试——签名定死、协议兼容、循环体未接电。"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from aegis.gateway.router import LLMGateway as RouterGateway
from aegis.gateway.schema import LLMChunk, LLMRequest
from aegis.runtime.runtime import AgentRuntime, GatewayLike
from aegis.runtime.spec import AgentSpec


class _NullGateway:
    """结构化满足 GatewayLike 的最小假网关——M2.1 阶段门面不该碰它。"""

    async def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        raise AssertionError("M2.1 门面不该调网关")
        yield  # 不可达；使其成为 async 生成器


def test_real_gateway_structurally_satisfies_protocol() -> None:
    """兼容性由 mypy 静态验证：内层函数永不执行，真网关签名若漂移，mypy 先红。"""

    def _accepts(g: GatewayLike) -> None: ...

    def _feed(real: RouterGateway) -> None:
        _accepts(real)

    assert True


async def test_run_signature_locked_but_not_implemented() -> None:
    """签名可用（DI + async 生成器惰性），循环体明确未接电。"""
    rt = AgentRuntime(gateway=_NullGateway())
    stream = rt.run(AgentSpec(system_prompt="x"), session_id="s-1", user_input="你好")
    with pytest.raises(NotImplementedError):
        await anext(stream)

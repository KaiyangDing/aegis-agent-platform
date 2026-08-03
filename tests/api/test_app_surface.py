"""M4.3：装配面安全不变量证人——mock 业务端点绝不挂上主应用（观察 ㉞，#47 薄层同批）。

"mock 绝不挂主 app"是 M3.7 拍板Ⅱ 的安全不变量（mock 子应用无认证，挂上即未认证
越权入口），此前只有 grep 能核、一行 include/mount 即可破且零红灯。断言用 mock
自己的路由集对主 app 求交集——mock 未来新增端点，断言面自动扩大，不靠硬编码
路径清单（封闭名单会静默过时）。
"""

from __future__ import annotations

from typing import Any

from fastapi.routing import APIRoute
from pydantic import SecretStr

from aegis.api.main import create_app
from aegis.apps.support.mock_backend.app import create_mock_api
from aegis.core.config import Settings
from aegis.runtime.runtime import AgentRuntime


class _NullGateway:
    def complete(self, req: Any) -> Any:  # pragma: no cover —— 装配面测试绝不触 LLM
        raise AssertionError("装配面测试绝不调用 LLM")


class _Limiter:
    async def try_take(self, scope: str, rate: float, capacity: float, cost: float = 1.0):  # pragma: no cover
        return (True, 0.0)


def _api_paths(app: Any) -> set[str]:
    """只取业务端点（APIRoute）：openapi/docs 等框架自带 Route 两 app 都有，属假交集面。"""
    return {r.path for r in app.routes if isinstance(r, APIRoute)}


async def test_mock_backend_routes_never_mount_on_main_app(db_session_factory) -> None:
    """主 app 与 mock 子应用的业务路由集必须零交集（全参注入，不碰生产单例链）。"""
    gw = _NullGateway()
    app = create_app(
        Settings(jwt_secret=SecretStr("m4-surface-secret-key-32bytes-min!")),
        session_factory=db_session_factory,
        runtime=AgentRuntime(gw, db_session_factory),
        limiter=_Limiter(),
        gateway=gw,
        approvals_lookup=db_session_factory,
    )
    mock_paths = _api_paths(create_mock_api(settings=Settings(), session_factory=db_session_factory))
    assert mock_paths, "mock 路由集为空——断言面失效，先查 create_mock_api"
    overlap = _api_paths(app) & mock_paths
    assert not overlap, f"mock 业务端点泄漏进主 app（未认证越权入口）：{overlap}"

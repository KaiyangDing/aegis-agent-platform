"""FastAPI 入口（M3.1/M3.2）：create_app 工厂——组装在边缘（app.state 挂共享资源）。

uvicorn 启动（仓库根）：uv run uvicorn aegis.api.main:create_app --factory
"""

from __future__ import annotations

from fastapi import FastAPI

from aegis.api import chat, usage
from aegis.api.ratelimit import InboundLimiterLike
from aegis.core.config import Settings, get_settings
from aegis.core.db import get_session_factory
from aegis.core.locks import build_session_lock
from aegis.core.redis import get_redis
from aegis.core.tenancy import SessionFactory
from aegis.gateway.factory import build_gateway
from aegis.gateway.ratelimit import RateLimiter
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec


def create_app(
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    runtime: AgentRuntime | None = None,
    limiter: InboundLimiterLike | None = None,
    agent_spec: AgentSpec | None = None,
) -> FastAPI:
    """应用工厂：五件可注入（测试传替身；生产缺省在此组装——组装在边缘的唯一聚合点）。

    生产缺省链：真网关 build_gateway() + 会话锁 build_session_lock()（M2.9 定案：
    生产必须显式传锁，lock=None 只属测试直通形态）+ 入站限流复用出站 RateLimiter（D6）。
    """
    s = settings or get_settings()
    factory = session_factory or get_session_factory()
    app = FastAPI(title="Aegis", version="0.1.0")
    app.state.settings = s
    app.state.session_factory = factory
    app.state.runtime = runtime or AgentRuntime(build_gateway(), factory, lock=build_session_lock())
    app.state.limiter = limiter or RateLimiter(get_redis(), replicas=s.replica_count)
    app.state.agent_spec = agent_spec or chat.PLACEHOLDER_SPEC
    app.include_router(usage.router)
    app.include_router(chat.router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:  # 存活探针（02 §9）：不查依赖，进程活着就 200
        return {"status": "ok"}

    return app

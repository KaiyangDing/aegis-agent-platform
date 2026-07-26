"""FastAPI 入口（M3.1/M3.2/M3.4/M3.8）：create_app 工厂——组装在边缘（app.state 挂共享资源）。

uvicorn 启动（仓库根）：uv run uvicorn aegis.api.main:create_app --factory
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI

from aegis.api import chat, kb, usage
from aegis.api.ratelimit import InboundLimiterLike
from aegis.apps.support.rag.retrieve import RetrievalProvider, Retriever
from aegis.apps.support.revalidate import build_precheck
from aegis.apps.support.service import ChatService
from aegis.core.config import Settings, get_settings
from aegis.core.db import get_session_factory
from aegis.core.locks import SessionLock, build_session_lock
from aegis.core.redis import get_redis
from aegis.core.tenancy import SessionFactory, TenantDirectory
from aegis.gateway.factory import build_embedding_client, build_gateway
from aegis.gateway.ratelimit import RateLimiter
from aegis.runtime.runtime import AgentRuntime, GatewayLike


def create_app(
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    runtime: AgentRuntime | None = None,
    limiter: InboundLimiterLike | None = None,
    enqueue: Callable[[str, str], None] | None = None,
    gateway: GatewayLike | None = None,
    chat_service: ChatService | None = None,
) -> FastAPI:
    """应用工厂：七件可注入（测试传替身；生产缺省在此组装——组装在边缘的唯一聚合点）。

    生产缺省链：真网关 build_gateway() + 会话锁 build_session_lock()（M2.9 定案）
    + **检索槽位生产接线**（M3.8 拍板Ⅱ：RetrievalProvider→AgentRuntime 受控缝，
    #7 收尾）+ 入站限流复用出站 RateLimiter（D6）+ 摄取入队 kb.build_enqueue
    + ChatService 编排层（M3.8②；PLACEHOLDER_SPEC 已退役——spec 按租户每请求装配）。
    注入 runtime 却不给 gateway/chat_service = 聊天不可用（chat 端点响亮失败）：
    kb/usage 类测试形态合法，聊天测试必须补 gateway。
    """
    s = settings or get_settings()
    factory = session_factory or get_session_factory()
    app = FastAPI(title="Aegis", version="0.1.0")
    app.state.settings = s
    app.state.session_factory = factory
    gw = gateway
    lock: SessionLock | None = None
    if runtime is None:
        gw = gw or build_gateway()
        lock = build_session_lock()
        retrieval = RetrievalProvider(Retriever(factory, build_embedding_client()))
        runtime = AgentRuntime(gw, factory, lock=lock, precheck=build_precheck(factory), retrieval=retrieval)
    app.state.runtime = runtime
    app.state.limiter = limiter or RateLimiter(get_redis(), replicas=s.replica_count)
    if chat_service is None and gw is not None:
        chat_service = ChatService(
            gateway=gw, factory=factory, directory=TenantDirectory(factory), runtime=runtime, lock=lock
        )
    app.state.chat_service = chat_service
    app.state.enqueue = enqueue or kb.build_enqueue(s)
    app.include_router(usage.router)
    app.include_router(chat.router)
    app.include_router(kb.router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:  # 存活探针（02 §9）：不查依赖，进程活着就 200
        return {"status": "ok"}

    return app

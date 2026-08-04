"""FastAPI 入口（M3.1/M3.2/M3.4/M3.8/M3.9/M3.10）：create_app 工厂——组装在边缘。

uvicorn 启动（仓库根）：uv run uvicorn aegis.api.main:create_app --factory
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import FileResponse

from aegis.api import approvals, chat, events_view, kb, metrics_view, stream, usage
from aegis.api.metrics_view import RequestCounterMiddleware
from aegis.api.notify import EventNotifier
from aegis.api.ratelimit import InboundLimiterLike
from aegis.apps.support.rag.retrieve import RetrievalProvider, Retriever
from aegis.apps.support.revalidate import build_precheck
from aegis.apps.support.service import ChatService
from aegis.core.config import Settings, get_settings
from aegis.core.db import get_owner_session_factory, get_session_factory
from aegis.core.locks import SessionLock, build_session_lock
from aegis.core.redis import get_redis
from aegis.core.tenancy import SessionFactory, TenantDirectory
from aegis.gateway.factory import build_embedding_client, build_gateway
from aegis.gateway.ratelimit import RateLimiter
from aegis.runtime.runtime import AgentRuntime, GatewayLike

logger = logging.getLogger(__name__)

_CHAT_PAGE = Path(__file__).resolve().parents[1] / "web" / "chat.html"
"""演示聊天页（M3.10④，01 §5 单文件无构建链）：Path(__file__) 锚定不依赖 cwd（07 §4 第 7 条）。"""


def create_app(
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    runtime: AgentRuntime | None = None,
    limiter: InboundLimiterLike | None = None,
    enqueue: Callable[[str, str], None] | None = None,
    gateway: GatewayLike | None = None,
    chat_service: ChatService | None = None,
    approvals_lookup: SessionFactory | None = None,
    notifier: EventNotifier | None = None,
    msg_redis: aioredis.Redis | None = None,
) -> FastAPI:
    """应用工厂：十件可注入（测试传替身；生产缺省在此组装——组装在边缘的唯一聚合点）。

    生产缺省链：真网关+会话锁+检索接线（M3.8 拍板Ⅱ）+前置校验（M3.9①）+入站限流
    +摄取入队+ChatService（M3.8②）+审批授权查读 owner 工厂（M3.9② 拍板Ⅲ）
    +**EventNotifier LISTEN 随 lifespan 起停**（M3.10③；测试 ASGITransport 不跑
    lifespan=天然降级轮询）+**msgbuf Redis 只在生产装配链接线**（M3.10②；注入
    runtime 的测试形态缺省 None、可显式注入）。
    注入 runtime 却不给 gateway/chat_service = 聊天与审批不可用（端点响亮失败）：
    kb/usage 类测试形态合法，聊天/审批/流式测试必须补 gateway。
    **中间组合的静默降级面（M4.7 ⑤(76) 显式声明，装配期各留一行日志）**：
    注入 runtime+gateway 而不给 chat_service → ChatService 以 lock=None 组装
    （直答/直通分支无会话互斥）；注入 runtime 而不给 msg_redis → 无 msgbuf
    （断线重连收不到 message_reset）。两者是测试形态的合法降级、生产装配链
    （全缺省）不可达——组合空间十件 2^n，逐组合响亮不现实，声明+日志+组合钉子
    （test_app_surface M4.7 节）是裁决过的防线形态。
    """
    s = settings or get_settings()
    factory = session_factory or get_session_factory()
    notify = notifier or EventNotifier(s.database_url_app)

    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await notify.start()
        try:
            yield
        finally:
            await notify.stop()

    app = FastAPI(title="Aegis", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(RequestCounterMiddleware)  # M4.2②：纯 ASGI 透传计数，对 SSE 零干扰
    app.state.settings = s
    app.state.session_factory = factory
    gw = gateway
    lock: SessionLock | None = None
    if runtime is None:
        gw = gw or build_gateway()
        lock = build_session_lock()
        retrieval = RetrievalProvider(Retriever(factory, build_embedding_client()))
        # M3.9①（#8）：批准后前置校验接线——M2.9 挂点在此通电，API 与 worker 共用同一模块
        runtime = AgentRuntime(gw, factory, lock=lock, precheck=build_precheck(factory), retrieval=retrieval)
        if msg_redis is None:
            msg_redis = get_redis()  # M3.10②：msgbuf 只在生产装配链接线
    app.state.runtime = runtime
    app.state.notifier = notify
    app.state.msg_redis = msg_redis
    app.state.limiter = limiter or RateLimiter(get_redis(), replicas=s.replica_count)
    if chat_service is None and gw is not None:
        if lock is None:
            logger.info("装配组合：外部注入 runtime——ChatService 以 lock=None 组装（直答/直通无会话互斥，测试形态）")
        if msg_redis is None:
            logger.info("装配组合：msg_redis 缺席——msgbuf 关闭（断线重连无 message_reset，测试形态）")
        chat_service = ChatService(
            gateway=gw,
            factory=factory,
            directory=TenantDirectory(factory),
            runtime=runtime,
            lock=lock,
            redis=msg_redis,
        )
    app.state.chat_service = chat_service
    app.state.enqueue = enqueue or kb.build_enqueue(s)
    app.state.approvals_lookup = approvals_lookup or get_owner_session_factory()
    app.include_router(usage.router)
    app.include_router(chat.router)
    app.include_router(kb.router)
    app.include_router(approvals.router)
    app.include_router(stream.router)
    app.include_router(events_view.router)
    app.include_router(metrics_view.router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:  # 存活探针（02 §9）：不查依赖，进程活着就 200
        return {"status": "ok"}

    @app.get("/chat")
    async def chat_page() -> FileResponse:  # 演示聊天页：同源出页（file:// 直开撞 CORS，不加中间件是刻意最小面）
        return FileResponse(_CHAT_PAGE, media_type="text/html; charset=utf-8")

    return app

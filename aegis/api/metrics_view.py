"""GET /metrics + HTTP 计数中间件（M4.2 交付②，00 §8.1）。

认证口径（M4.2 拍板 1，02 §7.1 已补行）：v1 无认证——防线=端口全程只绑
127.0.0.1（00 §2.2 安全底线）；生产形态应内网隔离或加 basic auth。
scrape 全程只读；DB 派生刷新走**平台维护面**工厂（app.state.approvals_lookup
——M3.9 拍板Ⅲ 的平台查读缝，events_view/stream 已把它用成通用缝）：
/metrics 无租户身份，app 工厂的 RLS 世界会把全部租户维度过滤成空集且零报错
（obs/metrics 模块头论证，(58) 家族）。
中间件取**纯 ASGI 形态**而非 BaseHTTPMiddleware：后者的 task-group 包装对
SSE 长流（chat/stream 端点，等待窗可达 25s）平添缓冲与取消语义风险；纯透传
只窥 http.response.start 一帧拿状态码，对流零干扰。
path label=路由模板（防 label 基数爆炸——真实路径含 session id 会把
Prometheus 内存打爆）；未匹配路由（404 探测）统一归并 "unmatched"，
不让任意外部可控 URL 变成 label 值。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response

from aegis.core.tenancy import SessionFactory
from aegis.obs.metrics import HTTP_REQUESTS, refresh_db_metrics, render

router = APIRouter()


@router.get("/metrics")
async def metrics(request: Request) -> Response:
    factory: SessionFactory = request.app.state.approvals_lookup  # 平台维护面（D4），见模块头
    await refresh_db_metrics(factory)  # 一族失败=留上次值+日志，绝不 500（obs 侧保证）
    body, content_type = render()
    return Response(content=body, media_type=content_type)


class RequestCounterMiddleware:
    """纯 ASGI 计数中间件：只窥状态码、只在请求收尾 +1，绝不改写任何帧。"""

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":  # lifespan/websocket 直通
            await self._app(scope, receive, send)
            return
        status_code = 500  # 响应头都没发出去就炸=按 500 计：异常也是流量，不数=盲区

        async def _send(message: Any) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self._app(scope, receive, _send)
        finally:
            # 路由匹配后 FastAPI 会把 route 放进 scope；未匹配（404 探测）无此键
            route = scope.get("route")
            path = getattr(route, "path_format", None) or getattr(route, "path", None) or "unmatched"
            HTTP_REQUESTS.labels(path=path, method=scope.get("method", "?"), status=str(status_code)).inc()

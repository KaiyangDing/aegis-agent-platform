"""FastAPI 入口（M3.1 交付②/④）：create_app 工厂——组装在边缘（app.state 挂共享资源）。

uvicorn 启动（仓库根）：uv run uvicorn aegis.api.main:create_app --factory
后续交付按需往 app.state 挂 directory/gateway（目录按需创建，00 §2.1 第 6 条）。
"""

from __future__ import annotations

from fastapi import FastAPI

from aegis.api import usage
from aegis.core.config import Settings, get_settings
from aegis.core.db import get_session_factory
from aegis.core.tenancy import SessionFactory


def create_app(settings: Settings | None = None, session_factory: SessionFactory | None = None) -> FastAPI:
    """应用工厂：settings/session_factory 可注入（测试传干净实例与 SAVEPOINT 夹具工厂，
    生产缺省走各自单例——组装在边缘）。"""
    app = FastAPI(title="Aegis", version="0.1.0")
    app.state.settings = settings or get_settings()
    app.state.session_factory = session_factory or get_session_factory()
    app.include_router(usage.router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:  # 存活探针（02 §9）：不查依赖，进程活着就 200
        return {"status": "ok"}

    return app

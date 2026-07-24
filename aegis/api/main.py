"""FastAPI 入口（M3.1 交付②）：create_app 工厂——组装在边缘（app.state 挂共享资源）。

uvicorn 启动（仓库根）：uv run uvicorn aegis.api.main:create_app --factory
后续交付按需往 app.state 挂 session_factory/directory/gateway（目录按需创建，00 §2.1 第 6 条）。
"""

from __future__ import annotations

from fastapi import FastAPI

from aegis.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """应用工厂：settings 可注入（测试传干净实例，生产缺省走 get_settings 单例）。"""
    app = FastAPI(title="Aegis", version="0.1.0")
    app.state.settings = settings or get_settings()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:  # 存活探针（02 §9）：不查依赖，进程活着就 200
        return {"status": "ok"}

    return app

"""mock 系统的进程内通路（M3.7 交付②）：ASGITransport 懒单例 + 任务局部安装缝。

拍板Ⅱ：mock 绝不挂载主 app——本客户端是唯一入口。global 手动单例（资源单例
惯例，00 §2.2 数据访问行）；懒创建=首个调用方所在 event loop 即宿主（API 进程
单 loop 形态）。测试不要用本单例：每测试自建 create_mock_api(...)+AsyncClient
（跨测试 event loop 复用单例会炸——get_redis/get_engine 同款教训，M2.9）。
"""

from __future__ import annotations

import httpx

from aegis.apps.support.mock_backend.app import create_mock_api
from aegis.core.loopcheck import LoopBoundGuard

_client: httpx.AsyncClient | None = None
_guard = LoopBoundGuard(
    "mock_client() 的进程内通路",
    hint="worker 任务体用 set_mock_client 安装任务局部实例（M3.9④）；测试每测自建。",
    strict=True,  # ㉝：本件契约本就禁止跨 loop 复用——直接抛人话；替身安装即重绑定天然豁免
)


def mock_client() -> httpx.AsyncClient:
    """进程级懒单例：首次调用时组装 mock 子应用与 ASGI 通路（组装在边缘）。"""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_mock_api()),
            base_url="http://mock-backend",
        )
    _guard.check(_client)  # M4.7 ㉝：跨 loop 复用=人话异常，不等 keep-alive 深处裸炸
    return _client


def set_mock_client(client: httpx.AsyncClient | None) -> None:
    """任务局部安装缝（M3.9④）：worker 每任务新 event loop，单例的 keep-alive 与
    底层 app 引擎都绑旧 loop——任务体现建现装、finally 归还 None（aclose 归调用方）。
    工具面（tools/_shared）只认 mock_client() 单点，穿参会改 L3 工具契约——装缝不改面。
    前提=--pool=solo 串行执行（06 §4；容器化 prefork 每进程独立同样成立，线程池不支持）。
    """
    global _client
    _client = client

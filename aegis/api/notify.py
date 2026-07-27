"""PG LISTEN/NOTIFY 事件通知（M3.10③，C22/#37 实装；plans §4.10/D10）。

独立 asyncpg 原生连接 LISTEN aegis_events——绝不从 SQLAlchemy 池借（LISTEN 绑定
物理连接，随事务归还即失聪，§7 陷阱 7）。按 payload "session_id:seq" 的 session
分发唤醒；断连/未启动=降级：wait_for 按轮询节拍返回、调用方重查增量（C22 兜底
=after_seq 轮询；后台任务持续重连自愈）。伪唤醒无害：等待方一律重查不信通知。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import asyncpg

logger = logging.getLogger(__name__)

_CHANNEL = "aegis_events"


def _raw_dsn(sqlalchemy_url: str) -> str:
    """SQLAlchemy URL → asyncpg 原生 DSN（剥 +asyncpg 方言段）。"""
    return sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://")


class EventNotifier:
    """LISTEN 管理器：start 起后台建连任务，wait_for 挂等待，stop 收尾。

    生产由 create_app lifespan 启停；测试不 start=恒降级轮询（ASGITransport
    不跑 lifespan——测试形态天然走 C22 兜底路径，零真实 LISTEN 依赖）。
    """

    def __init__(self, sqlalchemy_url: str, *, poll_interval_s: float = 2.0) -> None:
        self._dsn = _raw_dsn(sqlalchemy_url)
        self._poll_interval_s = poll_interval_s
        self._conn: asyncpg.Connection | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopped = False
        self._waiters: dict[str, set[asyncio.Event]] = {}

    async def start(self) -> None:
        if self._task is None:
            self._stopped = False
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def wait_for(self, session_id: str, *, timeout_s: float) -> None:
        """等"该会话可能有新事件"：通知/超时/降级节拍三者先到即返——本方法不携带
        任何数据，调用方一律重查增量（伪唤醒安全的根源）。"""
        if self._conn is None:
            await asyncio.sleep(min(timeout_s, self._poll_interval_s))  # 降级轮询节拍（C22）
            return
        event = asyncio.Event()
        bucket = self._waiters.setdefault(session_id, set())
        bucket.add(event)
        try:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(event.wait(), timeout_s)
        finally:
            bucket.discard(event)
            if not bucket:
                self._waiters.pop(session_id, None)

    def _on_notify(self, conn: asyncpg.Connection, pid: int, channel: str, payload: str) -> None:
        """asyncpg 回调（同步、事件循环内）：按 session 唤醒等待者。"""
        session_id = payload.rsplit(":", 1)[0]  # seq 段只作诊断，不消费（重查原则）
        for event in list(self._waiters.get(session_id, ())):
            event.set()

    async def _run(self) -> None:
        """建连-守连-重连循环：断连即降级（_conn=None → wait_for 走轮询），自愈不惊扰。"""
        while not self._stopped:
            conn: asyncpg.Connection | None = None
            try:
                conn = await asyncpg.connect(self._dsn)
                await conn.add_listener(_CHANNEL, self._on_notify)
                self._conn = conn
                logger.info("LISTEN %s 就绪", _CHANNEL)
                while not self._stopped and not conn.is_closed():
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("LISTEN 连接失败/中断，%.1fs 后重连（期间降级轮询）", self._poll_interval_s)
            finally:
                self._conn = None
                if conn is not None:
                    with contextlib.suppress(Exception):
                        await conn.close()
            if not self._stopped:
                await asyncio.sleep(self._poll_interval_s)

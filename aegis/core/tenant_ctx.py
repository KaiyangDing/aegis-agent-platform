"""租户上下文与 RLS 事务钩子（M3.3①，02 §7.2 / D2 / #18）。

每个事务开始时把 ContextVar 里的租户 id 经 set_config 注入 PG（第三参 true=事务级，
等价 SET LOCAL——事务结束即清、连接归池不残留，探针实证）；未设上下文注入空串，
current_setting 比对不中任何租户 → RLS fail-closed 空集。
D2 两条铁律：text() 具名绑定（SET 语句不能绑参、拼串有注入面；计划伪码的
exec_driver_sql+%s 在 asyncpg 方言是语法错——探针抓出的修正）；策略侧 text 比较
绝不 ::uuid（租户 id 形如 tenant-a，U1 陷阱）。
消费方：get_engine()（应用引擎装配时挂载）；请求路径 current_principal 设值（交付②）；
Celery 逐租户任务任务体首行设值（M3.4，#18）；维护面 owner 引擎不挂不设（D4）。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)
"""当前请求/任务的租户 id。None=未设（RLS 下读到空集）；每个 asyncio 任务持独立副本。"""

_SET_TENANT = text("SELECT set_config('app.tenant_id', :tid, true)")


@contextmanager
def tenant_context(tenant_id: str) -> Iterator[None]:
    """set/reset 成对：请求层、Celery 任务体、需代表特定租户查库的端点共用。"""
    token = current_tenant_id.set(tenant_id)
    try:
        yield
    finally:
        current_tenant_id.reset(token)


def install_tenant_guard(engine: AsyncEngine) -> None:
    """在应用引擎挂"begin"事件：BEGIN 后第一件事注入租户。只挂应用引擎，owner 不挂（D4）。"""

    @event.listens_for(engine.sync_engine, "begin")
    def _set_tenant(conn: Connection) -> None:  # 事件回调在 greenlet 内同步执行，收同步门面
        conn.execute(_SET_TENANT, {"tid": current_tenant_id.get() or ""})

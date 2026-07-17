"""Celery 应用（M2.10）：broker=Redis、无 result backend、beat 只挂 reaper 一条。

Windows 本地调试：`uv run celery -A aegis.workers.celery_app worker --pool=solo -l info`
（Celery 4 起官方放弃 Windows prefork——06 §4 第 1 坑）；beat 另开窗口或 `-B` 单进程；
生产形态 M4.7 容器化（Linux prefork）。broker 挂了 beat/worker 随之停摆 = 已接受降级
（ADR-005:45-47）：Redis 恢复后自愈，不写补偿代码；M3.4 摄取流水线与 M3.9 审批到期
扫描任务挂同一 app。
"""

from __future__ import annotations

from celery import Celery

from aegis.core.config import get_settings

celery_app = Celery(
    "aegis",
    broker=get_settings().redis_url,  # ADR-005 角色 4：Celery broker
    include=["aegis.workers.reaper"],  # 显式点名任务模块，不用 autodiscover（可 grep、可审计）
)
celery_app.conf.update(
    task_ignore_result=True,  # 无 result backend（3.2#9）：结果进日志与事件流，少一个 Redis 键面
    broker_connection_retry_on_startup=True,  # Celery 5.3+ 要求显式声明启动期重连策略（§7 陷阱 3）
    timezone="UTC",  # 调度时区显式钉死，不依赖主机时区
    enable_utc=True,
)
celery_app.conf.beat_schedule = {
    "reap-expired-leases": {
        "task": "aegis.workers.reaper.reap_expired_leases",
        "schedule": get_settings().reaper_interval_s,  # 秒数即间隔（P2：30s）
    }
}

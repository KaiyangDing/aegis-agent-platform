"""Celery 应用（M2.10）：broker=Redis、无 result backend、beat 挂 reaper 与审批对账两条。

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
    # 显式点名任务模块，不用 autodiscover（可 grep、可审计）；hitl 的 import 副作用
    # 同时完成真实恢复钩子注册（M3.9④ 拍板Ⅰ——worker 起=钩子在）
    include=["aegis.workers.ingest", "aegis.workers.reaper", "aegis.workers.hitl"],
)
celery_app.conf.update(
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # 至少一次投递：崩溃后消息仍在 unacked，会被重投
    task_reject_on_worker_lost=True,  # prefork 下子进程被杀时拒绝而非吞掉（solo 形态无事可做，M4.7 兑现）
)
celery_app.conf.beat_schedule = {
    "reap-expired-leases": {
        "task": "aegis.workers.reaper.reap_expired_leases",
        "schedule": get_settings().reaper_interval_s,  # 秒数即间隔（P2：30s）
    },
    "expire-approvals": {
        "task": "aegis.workers.hitl.expire_approvals",
        "schedule": get_settings().approval_scan_interval_s,  # M3.9：审批到期+对账（§4.9 决策 60s）
    },
}

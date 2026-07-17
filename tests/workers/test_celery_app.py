"""M2.10 交付③：celery_app 配置面（只读 conf，零 broker 连接——CI 无 Celery 依赖面）。"""

from __future__ import annotations

from aegis.core.config import get_settings
from aegis.workers.celery_app import celery_app


def test_broker_url_from_settings() -> None:
    """broker 取 Settings.redis_url（ADR-005 角色 4）——改配置不改代码。"""
    assert celery_app.conf.broker_url == get_settings().redis_url


def test_beat_schedule_has_reaper_entry() -> None:
    """beat 恰一条：键名/task 路径/间隔=Settings.reaper_interval_s（P2）。"""
    entry = celery_app.conf.beat_schedule["reap-expired-leases"]
    assert entry["task"] == "aegis.workers.reaper.reap_expired_leases"
    assert entry["schedule"] == get_settings().reaper_interval_s


def test_reaper_task_registered() -> None:
    """任务以显式 name 注册（include 点名，不靠 autodiscover）。"""
    import aegis.workers.reaper  # noqa: F401  # 触发任务注册（worker 由 include 完成同一件事）

    assert "aegis.workers.reaper.reap_expired_leases" in celery_app.tasks


def test_task_ignore_result_on() -> None:
    """无 result backend（3.2#9）：fire-and-forget，结果进日志与事件流。"""
    assert celery_app.conf.task_ignore_result is True

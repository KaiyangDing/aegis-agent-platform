"""M2.10 交付③：celery_app 配置面（只读 conf，零 broker 连接——CI 无 Celery 依赖面）。"""

from __future__ import annotations

from aegis.core.config import get_settings
from aegis.workers.celery_app import celery_app


def test_broker_url_from_settings() -> None:
    """broker 取 Settings.redis_url（ADR-005 角色 4）——改配置不改代码。"""
    assert celery_app.conf.broker_url == get_settings().redis_url


def test_beat_schedule_has_reaper_entry() -> None:
    """reaper 行：键名/task 路径/间隔=Settings.reaper_interval_s（P2）。
    （M3.9④ 起 beat 两条，"恰一条"旧口径随 expire-approvals 入驻作废。）"""
    entry = celery_app.conf.beat_schedule["reap-expired-leases"]
    assert entry["task"] == "aegis.workers.reaper.reap_expired_leases"
    assert entry["schedule"] == get_settings().reaper_interval_s


def test_beat_schedule_has_approval_sweep_entry() -> None:
    """M3.9④：审批对账行——task 路径/间隔=Settings.approval_scan_interval_s（§4.9 决策 60s）。"""
    entry = celery_app.conf.beat_schedule["expire-approvals"]
    assert entry["task"] == "aegis.workers.hitl.expire_approvals"
    assert entry["schedule"] == get_settings().approval_scan_interval_s


def test_reaper_task_registered() -> None:
    """任务以显式 name 注册（include 点名，不靠 autodiscover）。"""
    import aegis.workers.reaper  # noqa: F401  # 触发任务注册（worker 由 include 完成同一件事）

    assert "aegis.workers.reaper.reap_expired_leases" in celery_app.tasks


def test_hitl_task_registered() -> None:
    """M3.9④：hitl 模块任务同口径注册（include 点名第三员）。"""
    import aegis.workers.hitl  # noqa: F401

    assert "aegis.workers.hitl.expire_approvals" in celery_app.tasks


def test_task_ignore_result_on() -> None:
    """无 result backend（3.2#9）：fire-and-forget，结果进日志与事件流。"""
    assert celery_app.conf.task_ignore_result is True


def test_delivery_is_at_least_once() -> None:
    """M3 复盘补丁一（站 4 候选⑥）：投递语义钉死为"至少一次 × 幂等消费"。

    Celery 默认 acks_late=False 在任务执行**前**就 ack——worker 崩溃/被杀即消息
    永久消失，documents 卡在 PROCESSING 且无人兜底（reaper 只扫 sessions 租约）。
    改取至少一次的前提是三个任务体全部可重放，逐个有证：
    - ingest_document：四步收敛（test_ingest_resume.test_rerun_when_all_embedded_is_noop_done
      是"重投=零调用直落 DONE"的上界证词）；
    - reap_expired_leases / expire_approvals：周期对账型，每轮从库状态重推、
      赛跑由 CAS 裁出恰一赢家，重投与下一个 tick 无异。
    reject_on_worker_lost 覆盖另一种死法（prefork 子进程被杀；--pool=solo 无父进程
    故本地无事可做，M4.7 Linux prefork 兑现）。
    **为什么值得一条纯配置断言**：这两个值被回退时的故障形态是"文档静默丢失"——
    无异常、无日志、测试全绿，没有任何别的机制会喊。
    """
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True

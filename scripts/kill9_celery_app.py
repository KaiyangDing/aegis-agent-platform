"""kill -9 实录专用 Celery app（M4.0④b 实验装置，非生产件）。

**为什么需要它**：`task_acks_late=True` 只保证"消息不在执行前 ack"，真正把 unacked
消息放回队列的是 Redis transport 的 **`visibility_timeout`（默认 3600s）**——
生产取默认值是对的（00 §10.1 #48 的不变量：任务时长 ≪ visibility_timeout，
当前余量三个数量级），但实录不可能等一小时。

故本模块复用**生产 celery_app 与全部生产任务体**（import 即带 include 的三个任务模块），
只把这一个 transport 参数调小——与 M2.9 审批超时用注入时钟、M2.10 用可注入 clock
同款手法：**改的是实验装置的时间尺度，不是被测逻辑**。

调小到 60s 的依据（#48 原文的下限论证）：本实验任务时长 ≈3 批 × 3s ≈ 9s，
60s 是其 ~6.7 倍——仍满足"下限必须远大于最长任务时长"，不会退化成并发执行。
凭证里必须写明这个差异（简历数字纪律：口径随数字走）。

跑法（由 experiment_kill9_ingest.py 自动拉起，不必手工）：
    uv run celery -A scripts.kill9_celery_app worker --pool=solo -l info
"""

from __future__ import annotations

from aegis.workers.celery_app import celery_app

VISIBILITY_TIMEOUT_S = 60
"""实验尺度；生产为 Redis transport 默认 3600s（celery_app.py 不设=取默认）。"""

celery_app.conf.broker_transport_options = {"visibility_timeout": VISIBILITY_TIMEOUT_S}

__all__ = ["celery_app", "VISIBILITY_TIMEOUT_S"]

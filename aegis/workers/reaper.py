"""reaper（M2.10）：扫描过期租约 → CAS 抢租 → 钩子恢复；C9 超限置 failed + 审计事件。

薄同步壳 + async 内核（3.2#7）：reap_once 依赖全注入、可直测零 broker；
@task 壳只做 asyncio.run。worker 内每次任务用 NullPool 独立引擎（3.2#8：
asyncio.run 每次新建事件循环，asyncpg 连接绑定创建时的循环，复用全局
get_engine() 的池必炸"attached to a different loop"——那是 API 进程的资产）。
reaper 自身不 import 任何业务（apps）——恢复逻辑全在注册的钩子后面（3.2#11）。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aegis.core.config import get_settings
from aegis.runtime.events import EventType
from aegis.runtime.store import (
    EventWriter,
    LeaseStore,
    RunState,
    SessionFactory,
    SessionRecord,
    SessionStateStore,
    default_lease_owner,
)
from aegis.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

ResumeHook = Callable[[str, str, int], Awaitable[None]]
"""恢复钩子：(session_id, lease_owner, lease_generation)——实现负责装配 AgentSpec 并调
AgentRuntime.resume(spec, session_id, approval_id=None) 续跑。AgentSpec 由 L3 注入
（03 §1），M2 没有 L3——reaper 不可能自己装配 spec，故只抢租、恢复交给钩子；
M3.8 注册真实钩子，M2 测试与 kill -9 脚本注入演示钩子。"""

_resume_hook: ResumeHook | None = None


def register_resume_hook(hook: ResumeHook | None) -> None:
    """注册进程级恢复钩子（M3.8）；None 复位。

    未注册时 reaper 只抢租不恢复（3.2#11，日志警告）：该会话租约再次过期会被再抢、
    recovery_count 递增，最终 C9 置 failed——行为自洽、不悬空。
    """
    global _resume_hook
    _resume_hook = hook


@dataclass(frozen=True, slots=True)
class ReapReport:
    """一轮扫描的账目：scanned 过期候选数 / recovered 抢租成功 / abandoned C9 置 failed。"""

    scanned: int
    recovered: tuple[str, ...]
    abandoned: tuple[str, ...]


async def _session_snapshot(factory: SessionFactory, session_id: str) -> tuple[int, str | None, str]:
    """(recovery_count, lease_owner, run_state)——超限判定与审计 payload 的读源。"""
    async with factory() as s:
        row = (
            await s.execute(
                select(SessionRecord.recovery_count, SessionRecord.lease_owner, SessionRecord.run_state).where(
                    SessionRecord.id == session_id
                )
            )
        ).one_or_none()
    return (0, None, "") if row is None else (row[0], row[1], row[2])


async def reap_once(
    factory: SessionFactory,
    *,
    owner: str,
    lease_ttl_s: float,
    recovery_limit: int,
    resume: ResumeHook | None = None,
    now: datetime | None = None,
) -> ReapReport:
    """扫一轮：list_expired → 逐会话 steal（赢家恢复）/ 超限走 C9 终局。

    C9 终局（偏差 #7）：恰一次判定权在 T5 翻转（SessionStateStore.transition 的 CAS）——
    顺序 = 查快照判超限 → transition 判赢 → clear_lease 清扫 → 写审计事件；崩在缝上 =
    failed 无审计事件（接受，无谎言方向）。钩子异常批内隔离（P6）：reaper 是调度器
    不是执行器，单会话钩子炸不中断整批——该会话由后续轮次/C9 兜底，日志留痕。
    """
    leases = LeaseStore(factory)
    states = SessionStateStore(factory)
    ids = await leases.list_expired(now=now)
    recovered: list[str] = []
    abandoned: list[str] = []
    for sid in ids:
        generation = await leases.steal_expired(
            sid, owner=owner, ttl_s=lease_ttl_s, recovery_limit=recovery_limit, now=now
        )
        if generation is not None:
            recovered.append(sid)
            if resume is None:
                logger.warning("reaper 抢租未恢复（无钩子）：session=%s gen=%s——等待下轮或 C9", sid, generation)
                continue
            try:
                await resume(sid, owner, generation)
            except Exception:
                logger.exception("恢复钩子异常（批内隔离，P6）：session=%s", sid)
            continue
        # steal 打空：被并发赢家抢走，或已超限——查快照分辨（count 单调增，判定不会回退）
        count, last_owner, run_state = await _session_snapshot(factory, sid)
        if count < recovery_limit or run_state != RunState.RUNNING.value:
            continue  # 被并发赢家拿走 / 已被别的 reaper 置 failed
        if not await states.transition(sid, expected=RunState.RUNNING, to=RunState.FAILED):
            continue  # T5 输家安静（恰一次判定权在此，偏差 #7）
        await leases.clear_lease(sid)
        writer = await EventWriter.open(factory, sid, run_id=uuid4().hex)
        await writer.append(
            EventType.RECOVERY_ABANDONED,
            {"recovery_count": count, "recovery_limit": recovery_limit, "last_lease_owner": last_owner},
        )
        abandoned.append(sid)
    return ReapReport(scanned=len(ids), recovered=tuple(recovered), abandoned=tuple(abandoned))


async def _reap_fresh() -> ReapReport:
    """同步壳的 async 内胆：每次任务独立 NullPool 引擎，finally 归还（3.2#8/§7 陷阱 2）。"""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        return await reap_once(
            factory,
            owner=default_lease_owner(),
            lease_ttl_s=settings.lease_ttl_s,
            recovery_limit=settings.recovery_limit,
            resume=_resume_hook,
        )
    finally:
        await engine.dispose()


@celery_app.task(name="aegis.workers.reaper.reap_expired_leases")
def reap_expired_leases() -> dict[str, int]:
    """beat 周期任务的薄同步壳（3.2#7）：asyncio.run 包 async 内核，计数进 worker 日志。"""
    report = asyncio.run(_reap_fresh())
    logger.info(
        "reap 完成：scanned=%d recovered=%d abandoned=%d",
        report.scanned,
        len(report.recovered),
        len(report.abandoned),
    )
    return {"scanned": report.scanned, "recovered": len(report.recovered), "abandoned": len(report.abandoned)}

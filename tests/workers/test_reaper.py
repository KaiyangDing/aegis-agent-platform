"""M2.10 交付③：reap_once——抢租/钩子/幂等/双 reaper 赢家/C9 终局审计（零 broker 依赖）。

断言纪律：list_expired 是全库扫描——库里任何已提交的 running+过期行（如演示脚本残留）
都会进 report，断言一律过滤到本测试的会话，绝不对全局计数/集合做相等断言。
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from aegis.runtime.events import EventType
from aegis.runtime.store import EventRecord, EventWriter, RunState, SessionRecord
from aegis.workers.reaper import reap_once


async def _db_now(factory):
    async with factory() as s:
        return (await s.execute(select(func.now()))).scalar_one()


async def _mk(
    factory,
    sid: str,
    *,
    run_state: str = "running",
    owner: str | None = None,
    expires_in_s: float | None = None,
    recovery_count: int = 0,
) -> None:
    expires = None
    if expires_in_s is not None:
        expires = await _db_now(factory) + timedelta(seconds=expires_in_s)
    async with factory() as s:
        async with s.begin():
            s.add(
                SessionRecord(
                    id=sid,
                    tenant_id="t-a",
                    user_id="u-1",
                    run_state=run_state,
                    lease_owner=owner,
                    lease_expires_at=expires,
                    recovery_count=recovery_count,
                )
            )


async def _row(factory, sid: str) -> SessionRecord:
    async with factory() as s:
        return (await s.execute(select(SessionRecord).where(SessionRecord.id == sid))).scalar_one()


def _collecting_hook(into: list[tuple[str, str, int]]):
    async def hook(session_id: str, owner: str, generation: int) -> None:
        into.append((session_id, owner, generation))

    return hook


async def test_reap_once_steals_and_calls_resume(db_session_factory) -> None:
    """过期 running 会话：抢租成功、钩子收到 (sid, owner, generation)、report.recovered 命中。"""
    await _mk(db_session_factory, "rp-1", owner="dead:1", expires_in_s=-10)
    calls: list[tuple[str, str, int]] = []
    report = await reap_once(
        db_session_factory, owner="reaper:9", lease_ttl_s=60.0, recovery_limit=3, resume=_collecting_hook(calls)
    )
    assert "rp-1" in report.recovered
    assert [c for c in calls if c[0] == "rp-1"] == [("rp-1", "reaper:9", 1)]
    assert (await _row(db_session_factory, "rp-1")).recovery_count == 1


async def test_reap_once_skips_healthy_and_idle(db_session_factory) -> None:
    """活租约与 idle 不入扫描：scanned 只数过期候选（ix_sessions_reaper 的语义）。"""
    await _mk(db_session_factory, "rp-2a", owner="dead:1", expires_in_s=-10)
    await _mk(db_session_factory, "rp-2b", owner="ok:2", expires_in_s=60)
    await _mk(db_session_factory, "rp-2c", run_state="idle", owner="d:3", expires_in_s=-10)
    report = await reap_once(db_session_factory, owner="reaper:9", lease_ttl_s=60.0, recovery_limit=3)
    assert "rp-2a" in report.recovered
    assert "rp-2b" not in report.recovered  # 活租约不入扫描
    assert "rp-2c" not in report.recovered  # idle 不入扫描


async def test_reap_without_hook_still_steals(db_session_factory) -> None:
    """无钩子：只抢租不恢复、不炸（3.2#11）——等下轮或最终 C9，行为自洽不悬空。"""
    await _mk(db_session_factory, "rp-3", owner="dead:1", expires_in_s=-10)
    report = await reap_once(db_session_factory, owner="reaper:9", lease_ttl_s=60.0, recovery_limit=3, resume=None)
    assert "rp-3" in report.recovered
    assert (await _row(db_session_factory, "rp-3")).lease_owner == "reaper:9"


async def test_reap_over_limit_marks_failed_and_writes_audit(db_session_factory) -> None:
    """C9 终局：count=limit → T5 翻 failed + 清租约 + recovery_abandoned 三键审计事件。"""
    await _mk(db_session_factory, "rp-4", owner="dead:1", expires_in_s=-10, recovery_count=3)
    report = await reap_once(db_session_factory, owner="reaper:9", lease_ttl_s=60.0, recovery_limit=3)
    assert "rp-4" in report.abandoned
    row = await _row(db_session_factory, "rp-4")
    assert row.run_state == RunState.FAILED.value
    assert row.lease_owner is None
    async with db_session_factory() as s:
        event = (
            await s.execute(
                select(EventRecord).where(
                    EventRecord.session_id == "rp-4", EventRecord.type == EventType.RECOVERY_ABANDONED.value
                )
            )
        ).scalar_one()
    assert event.payload == {"recovery_count": 3, "recovery_limit": 3, "last_lease_owner": "dead:1"}


async def test_audit_event_continues_seq(db_session_factory) -> None:
    """审计事件接续旧流 seq（EventWriter.open 读流尾）——一次会话一条连续 trace。"""
    await _mk(db_session_factory, "rp-5", owner="dead:1", expires_in_s=-10, recovery_count=3)
    writer = await EventWriter.open(db_session_factory, "rp-5", "old-run")
    staged = await writer.append(EventType.USER_MESSAGE, {"content": "你好"})
    await reap_once(db_session_factory, owner="reaper:9", lease_ttl_s=60.0, recovery_limit=3)
    async with db_session_factory() as s:
        audit = (
            await s.execute(
                select(EventRecord).where(
                    EventRecord.session_id == "rp-5", EventRecord.type == EventType.RECOVERY_ABANDONED.value
                )
            )
        ).scalar_one()
    assert audit.seq == staged.seq + 1


async def test_reap_is_idempotent(db_session_factory) -> None:
    """同一 now 连跑两轮：第一轮抢租刷新了租约（now+ttl 未过期），第二轮零动作。"""
    await _mk(db_session_factory, "rp-6", owner="dead:1", expires_in_s=-10)
    now = await _db_now(db_session_factory)
    first = await reap_once(db_session_factory, owner="reaper:9", lease_ttl_s=60.0, recovery_limit=3, now=now)
    assert "rp-6" in first.recovered
    second = await reap_once(db_session_factory, owner="reaper:9", lease_ttl_s=60.0, recovery_limit=3, now=now)
    assert "rp-6" not in second.recovered  # 第一轮已把租约刷到 now+ttl，同 now 第二轮零动作
    assert "rp-6" not in second.abandoned


async def test_two_reapers_single_winner(db_session_factory) -> None:
    """双 reaper 赛跑：steal CAS 赢家恰一个——后到者面对已刷新的租约零动作。"""
    await _mk(db_session_factory, "rp-7", owner="dead:1", expires_in_s=-10)
    now = await _db_now(db_session_factory)
    r1 = await reap_once(db_session_factory, owner="reaper:1", lease_ttl_s=60.0, recovery_limit=3, now=now)
    r2 = await reap_once(db_session_factory, owner="reaper:2", lease_ttl_s=60.0, recovery_limit=3, now=now)
    assert "rp-7" in r1.recovered
    assert "rp-7" not in r2.recovered
    assert (await _row(db_session_factory, "rp-7")).lease_owner == "reaper:1"


async def test_resume_hook_failure_does_not_break_batch(db_session_factory) -> None:
    """P6 批内隔离：单会话钩子抛异常不中断整批——其余会话照常恢复，日志留痕。"""
    await _mk(db_session_factory, "rp-8a", owner="dead:1", expires_in_s=-20)
    await _mk(db_session_factory, "rp-8b", owner="dead:2", expires_in_s=-10)
    seen: list[str] = []

    async def boom_on_first(session_id: str, owner: str, generation: int) -> None:
        seen.append(session_id)
        if session_id == "rp-8a":
            raise RuntimeError("钩子爆炸")

    report = await reap_once(
        db_session_factory, owner="reaper:9", lease_ttl_s=60.0, recovery_limit=3, resume=boom_on_first
    )
    assert {"rp-8a", "rp-8b"} <= set(report.recovered)
    assert [s for s in seen if s.startswith("rp-8")] == ["rp-8a", "rp-8b"]  # 第二个会话的钩子照常被调

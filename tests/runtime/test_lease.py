"""M2.10 交付①：LeaseStore 六方法 CAS 语义（C2 围栏：条件进 WHERE、输赢看 rowcount）。

时钟纪律（m2.10 §7 陷阱 4）：db_conn 外层事务内 func.now() 恒定——过期场景一律直插
"相对 DB 钟的过去时刻"，绝不 sleep 等真钟（00 §2.2 时序断言不进 CI）。
run_state 永不被 LeaseStore 触碰（置位唯一路径=SessionStateStore.transition）。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from aegis.runtime.store import LeaseStore, RunState, SessionRecord, SessionStateStore


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
    generation: int = 0,
    recovery_count: int = 0,
) -> None:
    """直插会话行；expires_in_s 相对 DB 时钟（负值=已过期，None=租约时间列为空）。"""
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
                    lease_generation=generation,
                    recovery_count=recovery_count,
                )
            )


async def _row(factory, sid: str) -> SessionRecord:
    async with factory() as s:
        return (await s.execute(select(SessionRecord).where(SessionRecord.id == sid))).scalar_one()


async def test_acquire_fresh_session_bumps_generation(db_session_factory) -> None:
    """空租约的 running 行：acquire 返回 generation=1，owner/expires 落列，run_state 不被触碰。"""
    await _mk(db_session_factory, "ls-1")
    leases = LeaseStore(db_session_factory)
    assert await leases.acquire("ls-1", owner="host:1", ttl_s=60.0) == 1
    row = await _row(db_session_factory, "ls-1")
    assert row.lease_owner == "host:1"
    assert row.lease_expires_at is not None
    assert row.run_state == RunState.RUNNING.value


async def test_acquire_blocked_by_live_lease(db_session_factory) -> None:
    """活租约在他人手里 → None 且列不变；行非 running（idle）同样 → None（WHERE 前置条件）。"""
    await _mk(db_session_factory, "ls-2", owner="other:9", expires_in_s=60, generation=4)
    leases = LeaseStore(db_session_factory)
    assert await leases.acquire("ls-2", owner="me:1", ttl_s=60.0) is None
    row = await _row(db_session_factory, "ls-2")
    assert row.lease_owner == "other:9"
    assert row.lease_generation == 4
    await _mk(db_session_factory, "ls-2b", run_state="idle")
    assert await leases.acquire("ls-2b", owner="me:1", ttl_s=60.0) is None


async def test_acquire_after_expiry_succeeds(db_session_factory) -> None:
    """过期租约可被抢：generation 只增不减（5 → 6）。"""
    await _mk(db_session_factory, "ls-3", owner="dead:2", expires_in_s=-10, generation=5)
    leases = LeaseStore(db_session_factory)
    assert await leases.acquire("ls-3", owner="me:1", ttl_s=60.0) == 6
    assert (await _row(db_session_factory, "ls-3")).lease_owner == "me:1"


async def test_acquire_missing_row_returns_none(db_session_factory) -> None:
    """行不存在 → None（K5：与"租约在别人手里"同一形态，调用方前置 P2 校验保证行存在）。"""
    assert await LeaseStore(db_session_factory).acquire("ls-none", owner="me:1", ttl_s=60.0) is None


async def test_acquire_same_owner_reenters(db_session_factory) -> None:
    """同 owner 重入（偏差 #4）：reaper steal 后同进程 resume 再 acquire——活租约在自己名下照样成功。"""
    await _mk(db_session_factory, "ls-4", owner="me:1", expires_in_s=60, generation=7)
    leases = LeaseStore(db_session_factory)
    assert await leases.acquire("ls-4", owner="me:1", ttl_s=60.0) == 8
    assert await leases.acquire("ls-4", owner="other:2", ttl_s=60.0) is None  # 他人仍被挡


async def test_renew_extends_expiry(db_session_factory) -> None:
    """正确 (owner, generation) 续租成功且 expires 后移（同一恒定 DB 钟基准下 ttl 变大可比）。"""
    await _mk(db_session_factory, "ls-5")
    leases = LeaseStore(db_session_factory)
    gen = await leases.acquire("ls-5", owner="me:1", ttl_s=1.0)
    assert gen == 1
    before = (await _row(db_session_factory, "ls-5")).lease_expires_at
    assert await leases.renew("ls-5", owner="me:1", generation=1, ttl_s=3600.0) is True
    after = (await _row(db_session_factory, "ls-5")).lease_expires_at
    assert before is not None and after is not None
    assert after > before


async def test_renew_wrong_generation_is_fence(db_session_factory) -> None:
    """generation 失配 → False——围栏信号（C2 协议二：终态，调用方绝不退避重试）。"""
    await _mk(db_session_factory, "ls-6", owner="me:1", expires_in_s=60, generation=3)
    assert await LeaseStore(db_session_factory).renew("ls-6", owner="me:1", generation=2, ttl_s=60.0) is False


async def test_renew_wrong_owner_false(db_session_factory) -> None:
    """owner 不符 → False（所有权已转移，旧持有者的心跳打空）。"""
    await _mk(db_session_factory, "ls-7", owner="new:2", expires_in_s=60, generation=3)
    assert await LeaseStore(db_session_factory).renew("ls-7", owner="old:1", generation=3, ttl_s=60.0) is False


async def test_release_clears_lease_and_resets_recovery_count(db_session_factory) -> None:
    """干净收尾：租约双列清空 + recovery_count 归零（3.2#4——干净收尾证明会话不是毒的）；run_state 不动。"""
    await _mk(db_session_factory, "ls-8", owner="me:1", expires_in_s=60, generation=2, recovery_count=2)
    leases = LeaseStore(db_session_factory)
    assert await leases.release("ls-8", owner="me:1", generation=2) is True
    row = await _row(db_session_factory, "ls-8")
    assert row.lease_owner is None
    assert row.lease_expires_at is None
    assert row.recovery_count == 0
    assert row.run_state == RunState.RUNNING.value


async def test_release_after_steal_fails(db_session_factory) -> None:
    """被 steal 后旧持有者 release → False（generation 已 +1，旧凭据打空）。"""
    await _mk(db_session_factory, "ls-9", owner="old:1", expires_in_s=-5, generation=2)
    leases = LeaseStore(db_session_factory)
    assert await leases.steal_expired("ls-9", owner="reaper:9", ttl_s=60.0, recovery_limit=3) == 3
    assert await leases.release("ls-9", owner="old:1", generation=2) is False


async def test_steal_expired_increments_count_and_generation(db_session_factory) -> None:
    """抢租：generation +1 且 recovery_count +1（连续崩溃计数）。"""
    await _mk(db_session_factory, "ls-10", owner="dead:1", expires_in_s=-5, generation=1, recovery_count=1)
    leases = LeaseStore(db_session_factory)
    assert await leases.steal_expired("ls-10", owner="reaper:9", ttl_s=60.0, recovery_limit=3) == 2
    row = await _row(db_session_factory, "ls-10")
    assert row.recovery_count == 2
    assert row.lease_owner == "reaper:9"


@pytest.mark.parametrize(
    ("run_state", "expires_in_s"),
    [("idle", -5.0), ("awaiting_approval", -5.0), ("running", 60.0)],
)
async def test_steal_requires_running_and_expired(db_session_factory, run_state: str, expires_in_s: float) -> None:
    """steal 前置条件：非 running 或未过期 → None（挂起中的会话绝不被 reaper 抢）。"""
    sid = f"ls-11-{run_state}-{int(expires_in_s)}"
    await _mk(db_session_factory, sid, run_state=run_state, owner="a:1", expires_in_s=expires_in_s)
    assert await LeaseStore(db_session_factory).steal_expired(sid, owner="r:9", ttl_s=60.0, recovery_limit=3) is None


async def test_steal_over_limit_blocked_then_t5_wins_once(db_session_factory) -> None:
    """C9 终局（偏差 #7）：count=limit 时 steal 打空；恰一次判定权在 T5 翻转（transition CAS），
    赢家随后 clear_lease 清扫——mark_failed 的 lease 侧 CAS 因 NULL 兜底可重入而废弃。"""
    await _mk(db_session_factory, "ls-12", owner="dead:1", expires_in_s=-5, generation=3, recovery_count=3)
    leases = LeaseStore(db_session_factory)
    assert await leases.steal_expired("ls-12", owner="r:9", ttl_s=60.0, recovery_limit=3) is None
    st = SessionStateStore(db_session_factory)
    assert await st.transition("ls-12", expected=RunState.RUNNING, to=RunState.FAILED) is True  # 赢家
    assert await st.transition("ls-12", expected=RunState.RUNNING, to=RunState.FAILED) is False  # 输家安静
    await leases.clear_lease("ls-12")
    row = await _row(db_session_factory, "ls-12")
    assert row.lease_owner is None
    assert row.lease_expires_at is None
    assert row.run_state == RunState.FAILED.value


async def test_list_expired_filters_and_orders(db_session_factory) -> None:
    """只回 running+过期，按过期时间升序；活租约与 idle 不入列。"""
    await _mk(db_session_factory, "ls-13a", owner="d:1", expires_in_s=-30)
    await _mk(db_session_factory, "ls-13b", owner="d:2", expires_in_s=-10)
    await _mk(db_session_factory, "ls-13c", owner="ok:3", expires_in_s=60)
    await _mk(db_session_factory, "ls-13d", run_state="idle", owner="d:4", expires_in_s=-30)
    got = await LeaseStore(db_session_factory).list_expired()
    assert [s for s in got if s.startswith("ls-13")] == ["ls-13a", "ls-13b"]


async def test_list_expired_includes_null_lease(db_session_factory) -> None:
    """幽灵兜底（偏差 #5）：running 且租约 NULL 的行必须可被发现并可被 steal——
    否则 acquire 失败缝隙/T3 后崩溃留下的行永远无人认领。"""
    await _mk(db_session_factory, "ls-14")  # running、租约全 NULL
    leases = LeaseStore(db_session_factory)
    assert "ls-14" in await leases.list_expired()
    assert await leases.steal_expired("ls-14", owner="r:9", ttl_s=60.0, recovery_limit=3) == 1

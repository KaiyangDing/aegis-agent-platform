"""M2.2 交付④：审批 CAS 翻转——赢家恰一个、过期 fail-closed、可注入时钟。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from aegis.runtime.store import ApprovalRecord, ApprovalStatus, ApprovalStore


def _expires(hours: float) -> datetime:
    return datetime.now(UTC) + timedelta(hours=hours)


async def _create(store: ApprovalStore, aid: str, *, hours: float = 2.0) -> None:
    await store.create(
        approval_id=aid,
        session_id="s-ap",
        tenant_id="t-a",
        tool_name="refund_apply",
        args={"order_id": "1024", "amount": 350},
        expires_at=_expires(hours),
    )


async def _row(factory, aid: str) -> ApprovalRecord:
    async with factory() as s:
        return (await s.execute(select(ApprovalRecord).where(ApprovalRecord.id == aid))).scalar_one()


async def test_decide_approves_pending(db_session_factory) -> None:
    store = ApprovalStore(db_session_factory)
    await _create(store, "ap-1")
    assert await store.decide("ap-1", approved=True, operator_id="op-1") is True
    row = await _row(db_session_factory, "ap-1")
    assert row.status == ApprovalStatus.APPROVED
    assert row.operator_id == "op-1" and row.decided_at is not None


async def test_decide_rejects_pending(db_session_factory) -> None:
    store = ApprovalStore(db_session_factory)
    await _create(store, "ap-2")
    assert await store.decide("ap-2", approved=False, operator_id="op-1") is True
    row = await _row(db_session_factory, "ap-2")
    assert row.status == ApprovalStatus.REJECTED


async def test_second_decision_loses_and_never_overwrites(db_session_factory) -> None:
    """双坐席同点：赢家恰一个，输家的决定绝不覆盖赢家（C11 的核心语义）。"""
    store = ApprovalStore(db_session_factory)
    await _create(store, "ap-3")
    assert await store.decide("ap-3", approved=True, operator_id="op-快") is True
    assert await store.decide("ap-3", approved=False, operator_id="op-慢") is False
    row = await _row(db_session_factory, "ap-3")
    assert row.status == ApprovalStatus.APPROVED and row.operator_id == "op-快"


async def test_decide_refuses_expired_fail_closed(db_session_factory) -> None:
    """C7 fail-closed：过期单拒绝翻转——哪怕坐席点了批准，状态留给 reaper 翻 expired。"""
    store = ApprovalStore(db_session_factory)
    await _create(store, "ap-4", hours=-1.0)  # 已过期的 pending
    assert await store.decide("ap-4", approved=True, operator_id="op-1") is False
    row = await _row(db_session_factory, "ap-4")
    assert row.status == ApprovalStatus.PENDING and row.decided_at is None


async def test_cancel_pending(db_session_factory) -> None:
    store = ApprovalStore(db_session_factory)
    await _create(store, "ap-5")
    assert await store.cancel("ap-5") is True
    row = await _row(db_session_factory, "ap-5")
    assert row.status == ApprovalStatus.CANCELLED and row.operator_id is None


async def test_cancel_after_decision_loses(db_session_factory) -> None:
    """撤回与批准赛跑输了：终态不许被撤回改写。"""
    store = ApprovalStore(db_session_factory)
    await _create(store, "ap-6")
    assert await store.decide("ap-6", approved=True, operator_id="op-1") is True
    assert await store.cancel("ap-6") is False
    assert (await _row(db_session_factory, "ap-6")).status == ApprovalStatus.APPROVED


async def test_expire_due_flips_only_due_pending(db_session_factory) -> None:
    """到期扫描只碰"pending 且已到期"：未到期的、已终态的都不许动。"""
    store = ApprovalStore(db_session_factory)
    await _create(store, "ap-due", hours=-1.0)  # 已到期 pending → 应翻
    await _create(store, "ap-future", hours=10.0)  # 未到期 pending → 不动
    await _create(store, "ap-gone", hours=-1.0)  # 已到期但已撤回 → 不动
    await store.cancel("ap-gone")  # 过期单允许撤回（cancel 不查过期）
    flipped = await store.expire_due()
    assert flipped == ["ap-due"]
    assert (await _row(db_session_factory, "ap-due")).status == ApprovalStatus.EXPIRED
    assert (await _row(db_session_factory, "ap-future")).status == ApprovalStatus.PENDING
    assert (await _row(db_session_factory, "ap-gone")).status == ApprovalStatus.CANCELLED


async def test_expire_due_with_injected_clock(db_session_factory) -> None:
    """可注入时钟（C7）：不等真实时间走到 expires_at，把"未来的现在"递进去即触发。"""
    store = ApprovalStore(db_session_factory)
    await _create(store, "ap-7", hours=1.0)  # 对真实时钟而言未到期
    assert await store.expire_due() == []  # DB 时钟视角：还活着
    flipped = await store.expire_due(now=datetime.now(UTC) + timedelta(hours=2))
    assert flipped == ["ap-7"]
    assert (await _row(db_session_factory, "ap-7")).status == ApprovalStatus.EXPIRED

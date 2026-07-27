"""M3.9 交付④：审批对账扫描 sweep_once（调度逻辑直测零 broker）+ 真钩子注册。

sweep_once 与 reap_once 同款测法：factory/kick 全注入，SAVEPOINT 夹具直测；
生产装配壳（_sweep_fresh/_task_runtime/_resume_in_context）的真实链路归交付⑤
demo（kill/到期/撤回四段实录）——与 M2.10 reap 壳靠 kill -9 实录作证同口径。
断言全程过滤式（M2.10 教训）：本地库可能有真实演示残留（awaiting 会话/审批单），
只断言自家随机 id 的进出，绝不做全局相等。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from aegis.runtime.store import ApprovalRecord, ApprovalStatus, RunState, SessionRecord
from aegis.workers import hitl, reaper
from aegis.workers.hitl import sweep_once


class _KickSpy:
    def __init__(self, fail_sessions: set[str] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._fail = fail_sessions or set()

    async def __call__(self, session_id: str, approval_id: str) -> None:
        if session_id in self._fail:
            raise RuntimeError("kick 注入失败")
        self.calls.append((session_id, approval_id))


def _sid() -> str:
    return f"hitl-{uuid4().hex[:10]}"


async def _seed_session(factory, sid: str, *, run_state: str = RunState.AWAITING_APPROVAL.value) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=sid, tenant_id="t-hitl", user_id="u-h1", run_state=run_state))


async def _seed_approval(
    factory,
    sid: str,
    *,
    status: str = ApprovalStatus.PENDING.value,
    expires_delta: timedelta = timedelta(hours=1),
    created_delta: timedelta = timedelta(),
) -> str:
    """created_delta 显式给值：SAVEPOINT 夹具下同外层事务 now() 恒等，
    "最新单"排序在测试里必须靠显式 created_at 制造先后（生产中不同事务天然可序）。"""
    aid = f"ap-{uuid4().hex[:10]}"
    async with factory() as s:
        async with s.begin():
            s.add(
                ApprovalRecord(
                    id=aid,
                    session_id=sid,
                    tenant_id="t-hitl",
                    tool_name="refund_apply",
                    args={"order_id": "1024", "amount": 300},
                    status=status,
                    expires_at=datetime.now(UTC) + expires_delta,
                    created_at=datetime.now(UTC) + created_delta,
                )
            )
    return aid


async def _status(factory, aid: str) -> str:
    async with factory() as s:
        return (await s.execute(select(ApprovalRecord.status).where(ApprovalRecord.id == aid))).scalar_one()


async def test_sweep_flips_due_and_kicks_expired(db_session_factory) -> None:
    """到期链路一气呵成：pending 过期单被翻 EXPIRED，且同轮就被踢进恢复（终止路径）。"""
    sid = _sid()
    await _seed_session(db_session_factory, sid)
    aid = await _seed_approval(db_session_factory, sid, expires_delta=timedelta(hours=-1))
    spy = _KickSpy()
    report = await sweep_once(db_session_factory, kick=spy)
    assert aid in report.expired
    assert await _status(db_session_factory, aid) == ApprovalStatus.EXPIRED.value
    assert (sid, aid) in spy.calls
    assert (sid, aid) in report.kicked


async def test_sweep_kicks_decided_but_unresumed(db_session_factory) -> None:
    """W0 对账：decide 落锤后消费者崩了（approved+awaiting、无租约）——扫描把它捞回来。"""
    sid = _sid()
    await _seed_session(db_session_factory, sid)
    aid = await _seed_approval(db_session_factory, sid, status=ApprovalStatus.APPROVED.value)
    spy = _KickSpy()
    report = await sweep_once(db_session_factory, kick=spy)
    assert (sid, aid) in spy.calls
    assert aid not in report.expired  # 未到期，走的是"已决未续跑"判据而非到期翻转


async def test_sweep_leaves_pending_untouched(db_session_factory) -> None:
    """最新单 pending 且未到期=正常等待——扫描零动作（别把等待中的审批踢死）。"""
    sid = _sid()
    await _seed_session(db_session_factory, sid)
    aid = await _seed_approval(db_session_factory, sid)
    spy = _KickSpy()
    report = await sweep_once(db_session_factory, kick=spy)
    assert all(call_sid != sid for call_sid, _ in spy.calls)
    assert await _status(db_session_factory, aid) == ApprovalStatus.PENDING.value
    assert all(k_sid != sid for k_sid, _ in report.kicked)


async def test_sweep_ignores_non_awaiting_sessions(db_session_factory) -> None:
    """判据是会话态不是单据态：idle 会话的已决单不归 sweep 管（那是租约扫描/正常收尾的领地）。"""
    sid = _sid()
    await _seed_session(db_session_factory, sid, run_state=RunState.IDLE.value)
    await _seed_approval(db_session_factory, sid, status=ApprovalStatus.APPROVED.value)
    spy = _KickSpy()
    await sweep_once(db_session_factory, kick=spy)
    assert all(call_sid != sid for call_sid, _ in spy.calls)


async def test_sweep_latest_approval_wins(db_session_factory) -> None:
    """ "最新单"判据的存在理由：旧 EXPIRED 单 + 新 PENDING 单（新审批周期）时绝不踢——
    踢旧单会经 T3 掐掉正在等待新单的 run（14i 拍板Ⅵ 推演的误杀方向）。"""
    sid = _sid()
    await _seed_session(db_session_factory, sid)
    await _seed_approval(
        db_session_factory, sid, status=ApprovalStatus.EXPIRED.value, created_delta=timedelta(minutes=-10)
    )
    await _seed_approval(db_session_factory, sid)  # 最新：pending 未到期
    spy = _KickSpy()
    await sweep_once(db_session_factory, kick=spy)
    assert all(call_sid != sid for call_sid, _ in spy.calls)


async def test_sweep_kick_failure_is_isolated(db_session_factory) -> None:
    """单单隔离（reap_once P6 同款）：一单恢复炸了不中断整批，其余照踢、留痕不留摊。"""
    sid_bad, sid_ok = _sid(), _sid()
    await _seed_session(db_session_factory, sid_bad)
    await _seed_session(db_session_factory, sid_ok)
    await _seed_approval(db_session_factory, sid_bad, status=ApprovalStatus.APPROVED.value)
    aid_ok = await _seed_approval(db_session_factory, sid_ok, status=ApprovalStatus.APPROVED.value)
    spy = _KickSpy(fail_sessions={sid_bad})
    report = await sweep_once(db_session_factory, kick=spy)
    assert (sid_ok, aid_ok) in spy.calls
    assert all(k_sid != sid_bad for k_sid, _ in report.kicked)
    assert (sid_ok, aid_ok) in report.kicked


def test_module_import_registers_real_hook() -> None:
    """拍板Ⅰ收尾：import 本模块（celery include 同路径）即注册真实钩子——
    reaper 抢租后恢复不再"无钩子只抢租"。"""
    assert reaper._resume_hook is hitl.resume_session  # noqa: SLF001 —— 注册面取证

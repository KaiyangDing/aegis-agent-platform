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


async def test_task_runtime_releases_all_resources_on_partial_failure(monkeypatch) -> None:
    """M4.0② (63)：`_task_runtime` finally 五个串行 await 无各自保护——一个抛则其余泄漏。

    形态与 M2.12 偏差 #7（`_pump_with_lease` finally 次生异常顶掉原始异常）同族：
    长驻 worker 进程里每次任务泄漏一条 HTTP 连接池/Redis 连接/DB 引擎，累积成
    "跑了一天之后 worker 打不开新连接"——且首因（某个 aclose 抛）被淹没。

    测法：让**第一个** aclose 抛，断言其余三件仍被释放且归还顺序不变。
    未修代码：mock.aclose 抛出后 http/redis/engine 三件永不执行、异常裸传给调用方。
    修后语义：清理失败降级为 warning（清理不是调用方的业务错误，且它会顶掉 try 体内
    真正的首因异常——M2.12 偏差 #7 同族），但绝不阻断其余释放。
    """
    import httpx as _httpx
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine

    from aegis.workers import hitl as hitl_mod

    closed: list[str] = []

    class _Recorder:
        def __init__(self, name: str, *, boom: bool = False) -> None:
            self._name = name
            self._boom = boom

        async def aclose(self) -> None:
            if self._boom:
                raise RuntimeError(f"{self._name} 关闭失败")
            closed.append(self._name)

        async def dispose(self) -> None:
            closed.append(self._name)

    def _fake_mock_client(*a, **kw):
        return _Recorder("mock", boom=True)  # 第一个就炸

    monkeypatch.setattr(hitl_mod, "new_redis_client", lambda: _Recorder("redis"))
    monkeypatch.setattr(hitl_mod, "new_http_client", lambda: _Recorder("http"))
    monkeypatch.setattr(hitl_mod.httpx, "AsyncClient", _fake_mock_client)
    monkeypatch.setattr(hitl_mod, "create_async_engine", lambda *a, **kw: _Recorder("engine"))
    monkeypatch.setattr(hitl_mod, "install_tenant_guard", lambda engine: None)
    monkeypatch.setattr(hitl_mod, "async_sessionmaker", lambda *a, **kw: lambda: None)
    monkeypatch.setattr(hitl_mod, "build_gateway", lambda **kw: object())
    monkeypatch.setattr(hitl_mod, "build_session_lock", lambda **kw: None)
    monkeypatch.setattr(hitl_mod, "build_embedding_client", lambda *a, **kw: object())
    monkeypatch.setattr(hitl_mod, "build_precheck", lambda f: None)
    monkeypatch.setattr(hitl_mod, "RetrievalProvider", lambda r: None)
    monkeypatch.setattr(hitl_mod, "Retriever", lambda *a, **kw: None)
    monkeypatch.setattr(hitl_mod, "AgentRuntime", lambda *a, **kw: "runtime-stub")
    monkeypatch.setattr(hitl_mod, "create_mock_api", lambda *a, **kw: None)
    monkeypatch.setattr(hitl_mod, "set_mock_client", lambda c: None)

    async with hitl_mod._task_runtime() as rt:
        assert rt == "runtime-stub"

    # mock 的 aclose 抛了，其余四件仍须全部归还（顺序不变）
    assert closed == ["http", "redis", "engine"], f"资源泄漏：仅归还 {closed}"

    _ = (_httpx, _create_engine)  # 保持 import 显式（monkeypatch 目标来自模块属性）


async def test_sweep_reports_failed_kicks(db_session_factory) -> None:
    """(61)（M4.2③）：kick 失败进 failed 账目——单单隔离不再静默吞账（SweepReport 第四账）。"""
    ok_sid, bad_sid = _sid(), _sid()
    await _seed_session(db_session_factory, ok_sid)
    await _seed_session(db_session_factory, bad_sid)
    ok_aid = await _seed_approval(db_session_factory, ok_sid, status=ApprovalStatus.APPROVED.value)
    bad_aid = await _seed_approval(db_session_factory, bad_sid, status=ApprovalStatus.APPROVED.value)
    spy = _KickSpy(fail_sessions={bad_sid})
    report = await sweep_once(db_session_factory, kick=spy)
    assert (ok_sid, ok_aid) in report.kicked
    assert (bad_sid, bad_aid) in report.failed
    assert (bad_sid, bad_aid) not in report.kicked


async def test_sweep_caps_batch_and_logs(db_session_factory, monkeypatch, caplog) -> None:
    """(61)：扫描批上限（list_expired limit=100 先例）——触顶必留痕，绝不静默截断；
    余量由下一轮 beat 自愈（每轮从状态重推的红利）。计数断言不认名单（脏库纪律）。"""
    import logging

    monkeypatch.setattr(hitl, "_SWEEP_LIMIT", 1)
    for _ in range(2):
        await _seed_session(db_session_factory, _sid())
    with caplog.at_level(logging.WARNING, logger="aegis.workers.hitl"):
        report = await sweep_once(db_session_factory, kick=_KickSpy())
    assert report.waiting == 1  # 触顶：本轮只领一批
    assert any("对账扫描达批上限" in r.message for r in caplog.records)


async def test_sweep_flags_awaiting_without_any_ticket(db_session_factory, caplog) -> None:
    """(61)：awaiting 会话零审批单=不可能态——留痕不代管（不可能态留痕纪律归位，
    站 10 (61) 点名的 `latest is None` 静默 continue 从此有证词）。"""
    import logging

    sid = _sid()
    await _seed_session(db_session_factory, sid)
    with caplog.at_level(logging.WARNING, logger="aegis.workers.hitl"):
        report = await sweep_once(db_session_factory, kick=_KickSpy())
    assert any(sid in r.message and "无任何审批单" in r.message for r in caplog.records)
    assert all(pair[0] != sid for pair in report.kicked)

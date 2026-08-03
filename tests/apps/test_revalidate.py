"""M3.9 交付①：批准后前置校验（00 §10.1 #8——TOCTOU 显式防）的拒绝面与放行面。

被测对象是纯谓词层（build_precheck 闭包 factory）：veto 如何回填模型
（_PRECHECK_VETO_TEMPLATE / D19 否决不终止）已由 tests/runtime/
test_suspend_resume.py::test_precheck_veto_feeds_back_without_execution 钉死，
此处不重复穿 runtime。归属重校验不在本层（实况块 #5：PrecheckHook 无 ctx）——
批准执行走 executor 全程、handler 内 fetch_owned_order 以真实会话身份重跑归属，
本层只管参数快照对业务事实的新鲜度；RLS 场内限租由调用方环境承担（测试连接是
owner 形态、无 RLS，跨租户可见性归 tests/test_rls.py 的防线）。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import pytest

from aegis.apps.support.mock_backend.models import MockOrderRecord, MockOrderStatus
from aegis.apps.support.revalidate import REVALIDATORS, build_precheck


async def _seed_order(
    factory: Any, oid: str, *, status: str = MockOrderStatus.PAID.value, amount: str = "300.00"
) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(
                MockOrderRecord(
                    id=oid,
                    tenant_id="t-rv",
                    user_id="u-rv-1",
                    status=status,
                    paid_amount=Decimal(amount),
                    items={"sku": "R68 Pro"},
                )
            )


async def test_refund_pass_when_fresh(db_session_factory) -> None:
    """快照仍新鲜（订单可退、金额在上限内）→ None 放行。"""
    await _seed_order(db_session_factory, "rv-ok-1")
    precheck = build_precheck(db_session_factory)
    assert await precheck("refund_apply", {"order_id": "rv-ok-1", "amount": 80.0}) is None


async def test_refund_allows_exact_paid_amount(db_session_factory) -> None:
    """边界：金额恰等于可退上限放行——与 mock 拒绝面（严格大于才拒）逐字对齐。"""
    await _seed_order(db_session_factory, "rv-ok-2", amount="300.00")
    precheck = build_precheck(db_session_factory)
    assert await precheck("refund_apply", {"order_id": "rv-ok-2", "amount": 300.00}) is None


async def test_refund_rejects_refunded_order(db_session_factory, caplog) -> None:
    """TOCTOU 主场景：批准落锤前订单已退款 → 拒绝、不执行。

    M4.0② 候选②改判：拒因**不再点名"已退款"**（订单状态是他人可能不该知道的事实，
    见 `_STALE_TEXT` 论证）——observation 只钉"拒不拒"；M4.1③ 补上另一半：
    "为什么拒"进 detail（审计面，随 precheck_vetoed 事件落盘）与日志。
    """
    await _seed_order(db_session_factory, "rv-done-1", status=MockOrderStatus.REFUNDED.value)
    precheck = build_precheck(db_session_factory)
    with caplog.at_level(logging.WARNING, logger="aegis.apps.support.revalidate"):
        veto = await precheck("refund_apply", {"order_id": "rv-done-1", "amount": 80.0})
    assert veto is not None
    assert "已退款" not in veto.observation  # 不出线给模型
    assert veto.detail is not None and "已退款" in veto.detail  # 审计面拿到具体拒因
    assert any("已退款" in r.message for r in caplog.records)  # 日志面照旧可诊断


async def test_refund_rejects_over_paid_amount(db_session_factory) -> None:
    """金额超上限 → 拒绝：observation 不携带订单事实（M4.0②），detail 携带（M4.1③）。"""
    await _seed_order(db_session_factory, "rv-over-1", amount="300.00")
    precheck = build_precheck(db_session_factory)
    veto = await precheck("refund_apply", {"order_id": "rv-over-1", "amount": 300.01})
    assert veto is not None
    assert "300.00" not in veto.observation  # 他人订单的实付金额绝不出线给模型
    assert veto.detail is not None and "300.00" in veto.detail  # 上限值进审计面——排障不打折


async def test_order_derived_reasons_are_indistinguishable(db_session_factory, caplog) -> None:
    """M4.0② 候选②：三种订单派生拒因逐字节同话术——precheck 是统一话术的旁路。

    缺陷链：风险闸门在 handler **之前**（executor.py:148 vs :186），故"越权+超阈值"
    会先挂审批单；坐席批准后 `_load_order` **无 user 维度**（revalidate.py:41-45）
    读到同租户他人订单，拒因经 SYSTEM_PROMPT 规则 4「如实转达」复述给用户。
    四种拒因彼此可区分即存在性 oracle，而 `_shared.DENIED_TEXT` 三路同话术正为抹平它。
    执行面本就安全（handler 内 fetch_owned_order 照样挡住，站 8 口径⑵）——漏的是信息面。

    根因口径（站 10 口径⑴）：拿不到身份的层，输出必须对**所有**身份都安全。
    故订单派生的三种失败一律同话术；细节只进 logger（审计面照旧可诊断）。
    """
    await _seed_order(db_session_factory, "rv-uni-paid", amount="300.00")
    await _seed_order(db_session_factory, "rv-uni-done", status=MockOrderStatus.REFUNDED.value)
    precheck = build_precheck(db_session_factory)

    with caplog.at_level(logging.WARNING, logger="aegis.apps.support.revalidate"):
        over_limit = await precheck("refund_apply", {"order_id": "rv-uni-paid", "amount": 999.0})
        already_refunded = await precheck("refund_apply", {"order_id": "rv-uni-done", "amount": 10.0})
        not_found = await precheck("refund_apply", {"order_id": "rv-uni-ghost", "amount": 10.0})

    assert over_limit is not None and already_refunded is not None and not_found is not None
    # 模型面：三路 observation 逐字节同话术（oracle 抹平）
    assert over_limit.observation == already_refunded.observation == not_found.observation
    assert "300.00" not in over_limit.observation
    # 审计面（M4.1③）：三路 detail 互不相同——可区分性是审计面的职责，不是泄漏
    details = {over_limit.detail, already_refunded.detail, not_found.detail}
    assert None not in details and len(details) == 3
    # 日志面不打折：三次拒绝各留一条可诊断的 warning
    assert sum(1 for r in caplog.records if "前置校验拒绝" in r.message) == 3


async def test_order_derived_detail_carries_specifics(db_session_factory) -> None:
    """M4.1③ detail 契约：具体拒因（单号/上限）在审计面完整可诊断——
    trace API（仅 operator/admin）与日志由此对齐，坐席不再看到"批准了却没执行"的哑谜。"""
    await _seed_order(db_session_factory, "rv-dt-1", amount="300.00")
    precheck = build_precheck(db_session_factory)
    veto = await precheck("refund_apply", {"order_id": "rv-dt-1", "amount": 999.0})
    assert veto is not None and veto.detail is not None
    assert "rv-dt-1" in veto.detail  # 哪张单
    assert "999" in veto.detail and "300.00" in veto.detail  # 要多少、上限多少


async def test_malformed_amount_reason_may_stay_specific(db_session_factory) -> None:
    """反向边界：金额非法是**参数事实**不是订单事实——不泄露任何他人数据，可保持具体。

    这条划清了改判范围：粗粒度化只针对订单派生拒因，不是把所有反馈都抹平。
    """
    await _seed_order(db_session_factory, "rv-arg-1")
    precheck = build_precheck(db_session_factory)
    veto = await precheck("refund_apply", {"order_id": "rv-arg-1", "amount": -5})
    assert veto is not None and "正数" in veto.observation
    assert veto.detail is None  # 参数事实无审计增量：observation 已是全部信息


async def test_refund_rejects_missing_order(db_session_factory) -> None:
    """订单查无（或 RLS 场内不可见）→ fail-closed 拒绝；单号进审计面。"""
    precheck = build_precheck(db_session_factory)
    veto = await precheck("refund_apply", {"order_id": "rv-ghost", "amount": 10.0})
    assert veto is not None
    assert veto.detail is not None and "rv-ghost" in veto.detail


@pytest.mark.parametrize("bad_amount", ["abc", -1, 0])
async def test_refund_rejects_malformed_amount(db_session_factory, bad_amount: Any) -> None:
    """金额非法（非数/非正）→ 拒绝：校验器不信任快照里的任何字段形状。"""
    await _seed_order(db_session_factory, f"rv-bad-{bad_amount}")
    precheck = build_precheck(db_session_factory)
    veto = await precheck("refund_apply", {"order_id": f"rv-bad-{bad_amount}", "amount": bad_amount})
    assert veto is not None


async def test_coupon_pass_when_order_exists(db_session_factory) -> None:
    """补发校验器：订单在场且面额合法 → None（mock 侧补发不看订单状态，口径对齐）。"""
    await _seed_order(db_session_factory, "rv-cp-1")
    precheck = build_precheck(db_session_factory)
    assert await precheck("coupon_grant", {"order_id": "rv-cp-1", "amount": 20.0}) is None


async def test_coupon_rejects_missing_order(db_session_factory) -> None:
    precheck = build_precheck(db_session_factory)
    veto = await precheck("coupon_grant", {"order_id": "rv-cp-ghost", "amount": 20.0})
    assert veto is not None
    assert veto.detail is not None and "rv-cp-ghost" in veto.detail


async def test_unregistered_tool_fail_closed(db_session_factory, caplog) -> None:
    """走到 precheck 的必是挂过审批的工具；未登记校验器=登记漏了——
    fail-closed 拒绝 + warning 留痕（确定性安全闸门方向，00 §2.2 C34 分野左边）。"""
    precheck = build_precheck(db_session_factory)
    with caplog.at_level(logging.WARNING, logger="aegis.apps.support.revalidate"):
        veto = await precheck("order_query", {"order_id": "rv-any"})
    assert veto is not None and "order_query" in veto.observation
    assert veto.detail is None  # 配置病灶不涉他人订单事实，observation 即全部
    assert any("前置校验器" in r.message for r in caplog.records)


def test_registry_pins_gated_write_tools() -> None:
    """登记面契约钉死（#38 声明清单同款手法）：恰好覆盖两枚带风险闸门的写工具——
    少一枚=高危写批准后裸奔进 fail-closed 拒绝，多一枚=给不过审批的工具白造校验器。"""
    assert set(REVALIDATORS) == {"refund_apply", "coupon_grant"}


# ---------------------------------------------------------------------------
# M4.3 增量：(53) revalidate 与 mock 拒绝面的对齐证人
# ---------------------------------------------------------------------------

_ALIGN_CASES = [
    ("refund_apply", "paid", "50.00", True, "新鲜订单额度内：两侧同放"),
    ("refund_apply", "paid", "300.00", True, "恰等上限：> 是严格大于，最易漂的边界"),
    ("refund_apply", "paid", "300.01", False, "超上限：两侧同拒"),
    ("refund_apply", "refunded", "50.00", False, "已退款终态：两侧同拒"),
    ("refund_apply", None, "50.00", False, "订单不存在：两侧同拒"),
    ("coupon_grant", "refunded", "30.00", True, "补发不看状态：mock 放行，校验器不得更严"),
    ("coupon_grant", None, "30.00", False, "订单不存在：两侧同拒"),
]
_ALIGN_IDS = [
    "refund-fresh",
    "refund-exact-limit",
    "refund-over-limit",
    "refund-refunded",
    "refund-missing",
    "coupon-refunded-passes",
    "coupon-missing",
]


@pytest.mark.parametrize(("tool", "status", "amount", "both_pass", "why"), _ALIGN_CASES, ids=_ALIGN_IDS)
async def test_rejection_surface_stays_aligned_with_mock(
    db_session_factory, tool: str, status: str | None, amount: str, both_pass: bool, why: str
) -> None:
    """(53)：revalidate 与 mock 执行器"逐字对齐"首次有 CI 证人——同一份订单事实，
    校验器判定必须与下游执行判定一致（docstring 承诺从此有人作证）。

    漂移两方向危害不对称：revalidate 更松 = 漏一类 TOCTOU（还有 mock 409 兜底）；
    revalidate 更严 = **批准后白拒无人兜**（用户看到"已取消执行"而下游本会成功）。
    后者是主守方向——coupon-refunded-passes（终态订单补发照过）钉的就是它。
    顺序纪律：revalidate（纯读）先跑、mock（放行例会翻订单状态）后跑，互不污染。
    """
    import uuid

    import httpx

    from aegis.apps.support.mock_backend.app import create_mock_api
    from aegis.core.config import Settings

    oid = f"rv-align-{uuid.uuid4().hex[:8]}"
    if status is not None:
        await _seed_order(db_session_factory, oid, status=status)
    veto = await REVALIDATORS[tool](db_session_factory, {"order_id": oid, "amount": amount})
    reval_passes = veto is None

    app = create_mock_api(settings=Settings(), session_factory=db_session_factory)
    endpoint = "/refunds" if tool == "refund_apply" else "/coupons"
    body = {"tenant_id": "t-rv", "user_id": "u-rv-1", "order_id": oid, "amount": amount}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock") as c:
        resp = await c.post(endpoint, json=body, headers={"Idempotency-Key": uuid.uuid4().hex})
    mock_passes = resp.status_code == 200

    assert reval_passes == mock_passes == both_pass, (
        f"拒绝面漂移（{why}）：revalidate={'放行' if reval_passes else veto} / mock={resp.status_code}"
    )

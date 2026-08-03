"""批准后前置校验（M3.9 交付①，00 §10.1 #8——TOCTOU 显式防；M4.1③ 签名升级）。

审批的是参数快照（approvals.args）；批准落锤与执行之间业务事实可能已变——
重跑对象就是这份快照，失败=不执行、observation 回填模型（D19 否决不终止，
runtime._PRECHECK_VETO_TEMPLATE），否决本身由 L2 落 precheck_vetoed 审计事件。
签名冻结面：PrecheckHook=(tool_name, args) 无 ctx——归属重校验不在此层重复造：
批准执行走 executor 全程，handler 内 fetch_owned_order 以真实会话身份重跑归属；
本层只管快照的业务新鲜度。
DB 直读 mock_orders 而非走 mock API：故障注入不该误伤批准后的校验，
且躲开 mock_client 进程单例的跨 loop 面（worker 侧复用本模块）。
RLS 场内限租由调用方环境承担——本层不自设租户上下文（身份恒由边界建立）。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select

from aegis.apps.support.mock_backend.models import MockOrderRecord, MockOrderStatus
from aegis.core.tenancy import SessionFactory
from aegis.runtime.runtime import PrecheckHook, PrecheckVeto

logger = logging.getLogger(__name__)

Revalidator = Callable[[SessionFactory, Mapping[str, Any]], Awaitable[PrecheckVeto | None]]
"""单工具校验谓词：None=通过 / PrecheckVeto=拒绝（observation 给模型、detail 给审计）；
factory 由 build_precheck 闭包供给。"""

_STALE_TEXT = "订单当前状态不满足该操作的执行条件，已取消执行。"
"""订单派生拒因的统一话术（M4.0② 候选②）。

本层签名里没有 ctx（PrecheckHook 冻结面）——它读得到订单，却不知道请求者是谁。
拿不到身份的层，说出口的每句话都必须对**所有**身份安全（站 10 口径⑴）。
三种订单派生失败（不存在／已退款／超上限）若彼此可区分，合起来就是一个
存在性 + 状态 + 金额的 oracle：风险闸门在 handler **之前**（executor.py:148
vs :186），故"越权 + 超阈值"会先挂审批单，坐席批准后拒因经 SYSTEM_PROMPT
规则 4「如实转达」复述给用户——绕过 `_shared.DENIED_TEXT` 三路同话术的设计。
执行面本就安全（handler 内 fetch_owned_order 照样挡住，站 8 口径⑵），
本常量堵的是信息面。细节不丢（M4.1③ 补齐另一半）：具体拒因进 PrecheckVeto.detail
——随 precheck_vetoed 事件落盘（trace API 仅 operator/admin 可读）+ logger 留痕。
"""


def _as_positive_decimal(value: Any) -> Decimal | None:
    """快照字段不可信：非数/非正一律 None——校验器自己的入参防线。"""
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return dec if dec > 0 else None


async def _load_order(factory: SessionFactory, order_id: str) -> MockOrderRecord | None:
    """按单号读订单。无租户过滤参数——生产形态下 RLS（调用方环境上下文）自动限租；
    归属（用户级）的权威判定在批准执行时的 handler，不在这里。"""
    async with factory() as s:
        return (await s.execute(select(MockOrderRecord).where(MockOrderRecord.id == order_id))).scalar_one_or_none()


def _stale(detail: str) -> PrecheckVeto:
    """订单派生拒绝的唯一出口：observation 恒 _STALE_TEXT（模型面抹平 oracle）、
    detail 原样进审计面、日志同步留痕——三面一次成型，杜绝彼此漂移。"""
    logger.warning("前置校验拒绝：%s", detail)
    return PrecheckVeto(_STALE_TEXT, detail=detail)


async def _revalidate_refund(factory: SessionFactory, args: Mapping[str, Any]) -> PrecheckVeto | None:
    """退款新鲜度：订单在场、未退款、金额不超可退上限——与 mock 拒绝面逐字对齐
    （_execute_refund：status 终态与金额上限两道），拒绝面口径一处不漂移。

    订单派生的三种失败 observation 一律 _STALE_TEXT（候选②）；金额形状是**参数事实**，
    不泄露任何订单信息，故保持具体且无审计增量（detail=None）。
    """
    order_id = str(args.get("order_id", ""))
    order = await _load_order(factory, order_id)
    if order is None:
        return _stale(f"订单不存在或不可见：order={order_id}")
    if order.status == MockOrderStatus.REFUNDED.value:
        return _stale(f"订单已退款：order={order_id}")
    amount = _as_positive_decimal(args.get("amount"))
    if amount is None:
        return PrecheckVeto("退款金额非法（须为正数）")
    if amount > order.paid_amount:
        return _stale(f"退款金额超过可退上限：order={order_id} amount={amount} limit={order.paid_amount}")
    return None


async def _revalidate_coupon(factory: SessionFactory, args: Mapping[str, Any]) -> PrecheckVeto | None:
    """补发新鲜度：订单在场、面额合法即可——mock 侧补发不看订单状态（_execute_coupon），
    校验器不比业务系统更严：多拦=批准后白拒，口径以下游为准。
    订单派生拒因同 _revalidate_refund 走统一话术+审计细节（候选②/M4.1③）。
    """
    order_id = str(args.get("order_id", ""))
    order = await _load_order(factory, order_id)
    if order is None:
        return _stale(f"订单不存在或不可见：order={order_id}")
    if _as_positive_decimal(args.get("amount")) is None:
        return PrecheckVeto("补发面额非法（须为正数）")
    return None


REVALIDATORS: dict[str, Revalidator] = {
    "refund_apply": _revalidate_refund,
    "coupon_grant": _revalidate_coupon,
}
"""登记面=恰好两枚带 risk_policy 闸门的写工具（读工具与豁免写工具不过审批，
天然不进本表）；集合本身有契约测试钉死（#38 声明清单同款手法）。"""


def build_precheck(factory: SessionFactory) -> PrecheckHook:
    """组装前置校验钩子（注入 AgentRuntime(precheck=…)，API 与 worker 两侧共用）。

    未登记工具 fail-closed：走到 precheck 的必是挂过审批的工具，查不到校验器
    =登记漏了——确定性安全闸门方向，拒绝并留痕，不放行（C34 分野左边）。
    配置病灶不涉他人订单事实，observation 即全部信息（detail=None）。
    """

    async def precheck(tool_name: str, args: Mapping[str, Any]) -> PrecheckVeto | None:
        revalidator = REVALIDATORS.get(tool_name)
        if revalidator is None:
            logger.warning("审批工具未登记前置校验器，fail-closed 拒绝：tool=%s", tool_name)
            return PrecheckVeto(f"工具 {tool_name} 未登记前置校验器，按安全闸门拒绝")
        return await revalidator(factory, args)

    return precheck

"""M3.7 交付③：工具行为面——对抗③归属校验/幂等键接线(#6 全链)/#43 传输契约。

直接调 ToolDef.handler（executor 生命周期在 M2 已钉，这里测工具体内不变量）；
mock 通路经 monkeypatch 把 client._client 重定向到测试子应用（勿用生产单例）。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from aegis.apps.support.mock_backend import client as client_mod
from aegis.apps.support.mock_backend.app import create_mock_api
from aegis.apps.support.mock_backend.models import MockOrderRecord, MockWriteOpRecord
from aegis.apps.support.tools._shared import DENIED_TEXT
from aegis.apps.support.tools.coupons import coupon_grant
from aegis.apps.support.tools.logistics import logistics_query
from aegis.apps.support.tools.orders import order_query
from aegis.apps.support.tools.refunds import refund_apply
from aegis.apps.support.tools.tickets import ticket_create
from aegis.core.config import Settings
from aegis.runtime.tools import ToolContext


async def _seed_order(
    factory, oid: str, *, tenant: str = "t-mb", user: str = "u-mb-1", status: str = "paid", amount: str = "300.00"
) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(
                MockOrderRecord(
                    id=oid,
                    tenant_id=tenant,
                    user_id=user,
                    status=status,
                    paid_amount=Decimal(amount),
                    items={"sku": "R68 Pro"},
                )
            )


def _ctx(user: str = "u-mb-1", key: str = "tc-1") -> ToolContext:
    return ToolContext(tenant_id="t-mb", user_id=user, session_id="s-tools", run_id="r-1", tool_call_id=key)


@pytest.fixture
async def wired_mock(db_session_factory, monkeypatch):
    """mock 子应用建在测试工厂上，并把工具的进程内通路重定向过去（用完自动还原）。"""
    app = create_mock_api(settings=Settings(), session_factory=db_session_factory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock") as c:
        monkeypatch.setattr(client_mod, "_client", c)
        yield c


async def test_order_query_own_order_ok(wired_mock, db_session_factory) -> None:
    await _seed_order(db_session_factory, "mo-t-1", amount="199.99")
    out = await order_query.handler(_ctx(), order_id="mo-t-1")
    assert "error" not in out
    assert out["status"] == "paid"
    assert out["paid_amount"] == "199.99"


async def test_denial_uniform_three_ways(wired_mock, db_session_factory) -> None:
    """对抗③核心：他人订单/跨租户订单/不存在订单三种失败**逐字节同一话术**——不泄露差异。"""
    await _seed_order(db_session_factory, "mo-t-2", user="u-mb-2")  # 同租户他人
    await _seed_order(db_session_factory, "mo-t-3", tenant="t-other")  # 跨租户
    outs = [
        await order_query.handler(_ctx(), order_id="mo-t-2"),
        await order_query.handler(_ctx(), order_id="mo-t-3"),
        await order_query.handler(_ctx(), order_id="mo-t-none"),
    ]
    assert outs[0] == outs[1] == outs[2] == {"error": DENIED_TEXT}


async def test_logistics_roundtrip_and_denial(wired_mock, db_session_factory) -> None:
    """物流：本人单出轨迹；他人单与订单查询同一话术（归属校验是五工具共同底座）。"""
    await _seed_order(db_session_factory, "mo-t-4", status="shipped")
    await _seed_order(db_session_factory, "mo-t-5", user="u-mb-2")
    ok = await logistics_query.handler(_ctx(), order_id="mo-t-4")
    assert ok["track"] == ["已付款，商家备货中", "包裹已发出，运输中"]
    denied = await logistics_query.handler(_ctx(), order_id="mo-t-5")
    assert denied == {"error": DENIED_TEXT}


async def test_refund_chain_key_is_tool_call_id(wired_mock, db_session_factory) -> None:
    """#6 全链闭环的证明：台账行主键=ctx.tool_call_id——M2.4 透传的钥匙第一次真的开锁。"""
    await _seed_order(db_session_factory, "mo-t-6")
    out = await refund_apply.handler(_ctx(key="tc-refund-6"), order_id="mo-t-6", amount=50.0)
    assert out["duplicate"] is False
    assert out["status"] == "refunded"
    async with db_session_factory() as s:
        op = (
            await s.execute(select(MockWriteOpRecord).where(MockWriteOpRecord.idempotency_key == "tc-refund-6"))
        ).scalar_one()
    assert op.kind == "refund"
    assert op.payload["amount"] == "50.0"


async def test_refund_same_key_replays(wired_mock, db_session_factory) -> None:
    """恢复期语义下游证明：同一 tool_call_id 重发（reexecute 形态）→ 回放不重执行。"""
    await _seed_order(db_session_factory, "mo-t-7")
    first = await refund_apply.handler(_ctx(key="tc-refund-7"), order_id="mo-t-7", amount=60.0)
    again = await refund_apply.handler(_ctx(key="tc-refund-7"), order_id="mo-t-7", amount=60.0)
    assert first["duplicate"] is False
    assert again["duplicate"] is True
    async with db_session_factory() as s:
        ops = (
            await s.execute(select(MockWriteOpRecord).where(MockWriteOpRecord.idempotency_key == "tc-refund-7"))
        ).scalars()
    assert len(list(ops)) == 1


async def test_refund_denied_before_any_write(wired_mock, db_session_factory) -> None:
    """他人订单退款：拒绝发生在写请求发出之前——台账零行（对抗③的写面）。"""
    await _seed_order(db_session_factory, "mo-t-8", user="u-mb-2")
    out = await refund_apply.handler(_ctx(key="tc-refund-8"), order_id="mo-t-8", amount=10.0)
    assert out == {"error": DENIED_TEXT}
    async with db_session_factory() as s:
        rows = (
            await s.execute(select(MockWriteOpRecord).where(MockWriteOpRecord.idempotency_key == "tc-refund-8"))
        ).scalars()
    assert list(rows) == []


async def test_coupon_grant_ok(wired_mock, db_session_factory) -> None:
    await _seed_order(db_session_factory, "mo-t-9")
    out = await coupon_grant.handler(_ctx(key="tc-coupon-9"), order_id="mo-t-9", amount=10.0)
    assert out["granted"] is True
    async with db_session_factory() as s:
        op = (
            await s.execute(select(MockWriteOpRecord).where(MockWriteOpRecord.idempotency_key == "tc-coupon-9"))
        ).scalar_one()
    assert op.kind == "coupon"


async def test_ticket_create_ok(wired_mock) -> None:
    out = await ticket_create.handler(_ctx(key="tc-ticket-1"), title="投诉：物流太慢")
    assert out["ticket_id"]
    assert out["status"] == "open"


class _AmbiguousPost:
    """GET 正常、POST 按注入异常爆炸的通路替身——#43 条款的触发源。"""

    def __init__(self, real: httpx.AsyncClient, exc: Exception) -> None:
        self._real = real
        self._exc = exc

    async def get(self, *a: Any, **kw: Any) -> httpx.Response:
        return await self._real.get(*a, **kw)

    async def post(self, *a: Any, **kw: Any) -> httpx.Response:
        raise self._exc


async def test_write_transport_contract_43(wired_mock, db_session_factory, monkeypatch) -> None:
    """#43 契约（拍板Ⅰ）：发出后模糊（ReadError）→ TimeoutError 交 X1；
    连接未建立（ConnectError）→ 原样上抛=普通 ERROR 可改道。"""
    await _seed_order(db_session_factory, "mo-t-10")
    monkeypatch.setattr(client_mod, "_client", _AmbiguousPost(wired_mock, httpx.ReadError("对端半途重置")))
    with pytest.raises(TimeoutError):
        await refund_apply.handler(_ctx(key="tc-43-a"), order_id="mo-t-10", amount=10.0)
    monkeypatch.setattr(client_mod, "_client", _AmbiguousPost(wired_mock, httpx.ConnectError("拒绝连接")))
    with pytest.raises(httpx.ConnectError):
        await refund_apply.handler(_ctx(key="tc-43-b"), order_id="mo-t-10", amount=10.0)

"""M3.7 交付②：进程内模拟业务系统——四端点行为/去重算法/故障注入。

每测试自建 create_mock_api(session_factory=db_session_factory) + ASGITransport 客户端
（不用 client.mock_client 单例——那是 API 进程的通路，跨测试 event loop 会炸）；
db_session_factory 是 owner 连接（RLS 面在 tests/test_rls.py，本文件管行为语义）。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from aegis.apps.support.mock_backend.app import create_mock_api
from aegis.apps.support.mock_backend.models import MockOrderRecord, MockWriteOpRecord
from aegis.core.config import Settings


async def _seed_order(factory, oid: str, *, status: str = "paid", amount: str = "300.00") -> None:
    async with factory() as s:
        async with s.begin():
            s.add(
                MockOrderRecord(
                    id=oid,
                    tenant_id="t-mb",
                    user_id="u-mb-1",
                    status=status,
                    paid_amount=Decimal(amount),
                    items={"sku": "R68 Pro"},
                )
            )


@pytest.fixture
async def mock_http(db_session_factory):
    app = create_mock_api(settings=Settings(), session_factory=db_session_factory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock") as c:
        yield c


_REFUND = {"tenant_id": "t-mb", "user_id": "u-mb-1", "order_id": "mo-api-r1", "amount": "50.00"}


# ---- 读端点 ----


async def test_get_order_roundtrip(mock_http, db_session_factory) -> None:
    """读端点：租户过滤 WHERE 命中；金额以字符串出线（钱不过 float 延伸到 mock 线格式）。"""
    await _seed_order(db_session_factory, "mo-api-g1", amount="199.99")
    r = await mock_http.get("/orders/mo-api-g1", params={"tenant_id": "t-mb"})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "mo-api-g1"
    assert body["user_id"] == "u-mb-1"  # 归属判定的原料：mock 交出行，判定权在工具（交付③）
    assert body["paid_amount"] == "199.99"
    assert body["status"] == "paid"


async def test_get_order_wrong_tenant_is_404(mock_http, db_session_factory) -> None:
    """跨租户读=查无此单：mock 侧 WHERE tenant_id 第一层（RLS 第二层在 test_rls）。"""
    await _seed_order(db_session_factory, "mo-api-g2")
    r = await mock_http.get("/orders/mo-api-g2", params={"tenant_id": "t-other"})
    assert r.status_code == 404


async def test_get_unknown_order_is_404(mock_http) -> None:
    r = await mock_http.get("/orders/mo-api-none", params={"tenant_id": "t-mb"})
    assert r.status_code == 404


async def test_logistics_track_derives_from_status(mock_http, db_session_factory) -> None:
    """伪轨迹是订单状态的确定性派生（零随机）：shipped 两段、refunded 终止文案。"""
    await _seed_order(db_session_factory, "mo-api-l1", status="shipped")
    await _seed_order(db_session_factory, "mo-api-l2", status="refunded")
    r1 = await mock_http.get("/logistics/mo-api-l1", params={"tenant_id": "t-mb"})
    assert r1.status_code == 200
    assert len(r1.json()["track"]) == 2
    r2 = await mock_http.get("/logistics/mo-api-l2", params={"tenant_id": "t-mb"})
    assert r2.json()["track"] == ["订单已退款，物流终止"]


async def test_logistics_unknown_order_is_404(mock_http) -> None:
    r = await mock_http.get("/logistics/mo-api-none", params={"tenant_id": "t-mb"})
    assert r.status_code == 404


# ---- tickets（M4.7 ㊳：台账去重与 refunds/coupons 同款；收件箱仍内存 D9）----


async def test_ticket_create_returns_id(mock_http) -> None:
    """带键建单：ticket_id 铸造并入台账 payload（收件箱重启即清的取舍不变）。"""
    body = {"tenant_id": "t-mb", "user_id": "u-mb-1", "title": "投诉", "detail": "很生气"}
    r = await mock_http.post("/tickets", json=body, headers={"Idempotency-Key": f"tk-{uuid4().hex}"})
    assert r.status_code == 200
    assert r.json()["ticket_id"]
    assert r.json()["status"] == "open"
    assert r.json()["duplicate"] is False


async def test_ticket_missing_idempotency_key_is_400(mock_http) -> None:
    """M4.7 ㊳：/tickets 此前连 Idempotency-Key 头都不读（"写工具一律带键"兑现率 2/3，
    ticket_create 送出的键被静默丢弃）——现与 refunds 同款缺键 400。"""
    body = {"tenant_id": "t-mb", "user_id": "u-mb-1", "title": "投诉", "detail": "x"}
    assert (await mock_http.post("/tickets", json=body)).status_code == 400


async def test_ticket_same_key_replays_same_ticket_id(mock_http) -> None:
    """M4.7 ㊳ 主证人：同键重放拿到**同一个** ticket_id——崩溃重试不再产孤儿单
    （handoff 建单成功后崩、恢复重试的剧本自此有去重兜底）。"""
    key = f"tk-{uuid4().hex}"
    body = {"tenant_id": "t-mb", "user_id": "u-mb-1", "title": "转人工", "detail": "s"}
    first = (await mock_http.post("/tickets", json=body, headers={"Idempotency-Key": key})).json()
    second = (await mock_http.post("/tickets", json=body, headers={"Idempotency-Key": key})).json()
    assert first["duplicate"] is False and second["duplicate"] is True
    assert second["ticket_id"] == first["ticket_id"]


# ---- 写端点：去重算法（#6 下游端）----


async def test_refund_missing_idempotency_key_is_400(mock_http) -> None:
    """缺键 400：逼调用方永远带键——没有钥匙的去重是装饰品（§4.7 算法第 1 步）。"""
    r = await mock_http.post("/refunds", json=dict(_REFUND))
    assert r.status_code == 400


async def test_replay_read_is_tenant_scoped_loud(mock_http, db_session_factory) -> None:
    """M4.7 ㉙：回放读带租户过滤——跨租撞键响亮 NoResultFound（**无 RLS 的世界也**成立），
    绝不静默借用他租台账。此前回放 SELECT 不带租户，是全模块唯一"交叉核验退化成
    单层"处，安全全靠"键是 uuid4 不可控"+"RLS 在场"两条外部条件。"""
    await _seed_order(db_session_factory, "mo-api-x29", amount="80.00")
    key = f"rf-{uuid4().hex}"
    body = {**_REFUND, "order_id": "mo-api-x29"}
    first = await mock_http.post("/refunds", json=body, headers={"Idempotency-Key": key})
    assert first.status_code == 200 and first.json()["duplicate"] is False
    with pytest.raises(NoResultFound):
        await mock_http.post("/refunds", json={**body, "tenant_id": "t-other"}, headers={"Idempotency-Key": key})


async def test_refund_executes_and_marks_order(mock_http, db_session_factory) -> None:
    """首击全链：duplicate=False、订单置 refunded、台账行 kind/payload 快照在场。"""
    await _seed_order(db_session_factory, "mo-api-r1")
    r = await mock_http.post("/refunds", json=dict(_REFUND), headers={"Idempotency-Key": "wo-api-k1"})
    assert r.status_code == 200
    body = r.json()
    assert body["duplicate"] is False
    assert body["status"] == "refunded"
    async with db_session_factory() as s:
        order = (await s.execute(select(MockOrderRecord).where(MockOrderRecord.id == "mo-api-r1"))).scalar_one()
        op = (
            await s.execute(select(MockWriteOpRecord).where(MockWriteOpRecord.idempotency_key == "wo-api-k1"))
        ).scalar_one()
    assert order.status == "refunded"
    assert op.kind == "refund"
    assert op.payload["amount"] == "50.00"


async def test_refund_double_click_replays_first_result(mock_http, db_session_factory) -> None:
    """#6 核心：同键二击回放台账不重执行——第二击金额故意不同，返回的却是首击快照。"""
    await _seed_order(db_session_factory, "mo-api-r2")
    first = dict(_REFUND, order_id="mo-api-r2", amount="60.00")
    second = dict(first, amount="99.00")  # 同键即同操作：参数差异被无视，防模型紊乱参数重发
    k = {"Idempotency-Key": "wo-api-k2"}
    r1 = await mock_http.post("/refunds", json=first, headers=k)
    r2 = await mock_http.post("/refunds", json=second, headers=k)
    assert r1.json()["duplicate"] is False
    assert r2.json()["duplicate"] is True
    assert r2.json()["amount"] == "60.00"  # 回放首击结果快照
    async with db_session_factory() as s:
        ops = (
            await s.execute(select(MockWriteOpRecord).where(MockWriteOpRecord.idempotency_key == "wo-api-k2"))
        ).scalars()
    assert len(list(ops)) == 1


async def test_refund_validation_failure_does_not_burn_key(mock_http, db_session_factory) -> None:
    """失败不烧钥匙：可退性校验不过=整事务回滚（连 claim 一起撤），同键重试仍可成功。"""
    await _seed_order(db_session_factory, "mo-api-r3", amount="100.00")
    k = {"Idempotency-Key": "wo-api-k3"}
    bad = dict(_REFUND, order_id="mo-api-r3", amount="999.00")
    r1 = await mock_http.post("/refunds", json=bad, headers=k)
    assert r1.status_code == 409
    good = dict(bad, amount="80.00")
    r2 = await mock_http.post("/refunds", json=good, headers=k)
    assert r2.status_code == 200
    assert r2.json()["duplicate"] is False


async def test_refund_refunded_order_conflict(mock_http, db_session_factory) -> None:
    """已退款订单再退（新键）→ 409：状态终态是可退性校验的拒绝依据。"""
    await _seed_order(db_session_factory, "mo-api-r4", status="refunded")
    body = dict(_REFUND, order_id="mo-api-r4")
    r = await mock_http.post("/refunds", json=body, headers={"Idempotency-Key": "wo-api-k4"})
    assert r.status_code == 409


async def test_coupon_reuses_same_algorithm_and_table(mock_http, db_session_factory) -> None:
    """coupons=同表 kind='coupon' 同算法（半天规模的来源）；补发不动订单状态。"""
    await _seed_order(db_session_factory, "mo-api-c1")
    k = {"Idempotency-Key": "wo-api-k5"}
    body = dict(_REFUND, order_id="mo-api-c1", amount="10.00")
    r1 = await mock_http.post("/coupons", json=body, headers=k)
    r2 = await mock_http.post("/coupons", json=body, headers=k)
    assert r1.json()["duplicate"] is False
    assert r2.json()["duplicate"] is True
    async with db_session_factory() as s:
        op = (
            await s.execute(select(MockWriteOpRecord).where(MockWriteOpRecord.idempotency_key == "wo-api-k5"))
        ).scalar_one()
        order = (await s.execute(select(MockOrderRecord).where(MockOrderRecord.id == "mo-api-c1"))).scalar_one()
    assert op.kind == "coupon"
    assert order.status == "paid"


# ---- 故障注入 ----


async def test_fault_injection_error_rate_returns_503(db_session_factory) -> None:
    """mock_error_rate=1.0 → 恒 503：X1"结果不明"剧本的发生器（latency 属时序断言不进 CI）。"""
    app = create_mock_api(settings=Settings(mock_error_rate=1.0), session_factory=db_session_factory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock") as c:
        r = await c.get("/orders/any", params={"tenant_id": "t-mb"})
    assert r.status_code == 503

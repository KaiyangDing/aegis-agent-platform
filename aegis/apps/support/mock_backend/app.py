"""进程内模拟业务系统（M3.7 交付②，plans §4.7 / D9）。

「独立部署模拟业务系统」永久简化为进程内子应用（00 §10.3）：httpx.ASGITransport
调用即真 HTTP 语义、零网络。mock 信任内部调用方（tenant_id/user_id 是裸参数），
因此**绝不挂载到主 app**（拍板Ⅱ：挂上去=未认证水平越权入口）——对外唯一通路是
client.mock_client() 的进程内 transport。读端点只按租户过滤：mock 交出行、
归属判定权在工具（交付③ 比对 ctx）——防线不从工具漂到 mock。

去重（#6 下游端）：POST /refunds、/coupons 共用一套算法——Idempotency-Key 缺失
400；claim（ON CONFLICT DO NOTHING）撞键即回放台账 payload；首次则校验+执行+
回填**同一事务**：崩溃零中间态（要么全有要么全无），校验失败整事务回滚=失败
不烧钥匙。

故障注入中间件按 Settings.mock_error_rate / mock_latency_ms 工作——演示"写超时
→X1 结果不明→查询确认"剧本的发生器（prod 禁开，config 校验器扩展）。
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import CursorResult, Result, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from aegis.apps.support.mock_backend.models import MockOrderRecord, MockOrderStatus, MockWriteOpRecord
from aegis.core.config import Settings, get_settings
from aegis.core.db import get_session_factory
from aegis.core.tenancy import SessionFactory

_TRACKS = {
    MockOrderStatus.PAID.value: ["已付款，商家备货中"],
    MockOrderStatus.SHIPPED.value: ["已付款，商家备货中", "包裹已发出，运输中"],
    MockOrderStatus.DELIVERED.value: ["已付款，商家备货中", "包裹已发出，运输中", "已送达并签收"],
    MockOrderStatus.REFUNDED.value: ["订单已退款，物流终止"],
}
"""伪轨迹=订单状态的确定性派生（零随机）：mock 的可预测性是测试与演示资产。"""


class WriteOpIn(BaseModel):
    """写操作请求体（refund/coupon 同形）。amount 走 Decimal：工具侧传字符串
    （"50.00"）精确入账，数字也经 pydantic str 中转——钱不过 float 的线格式面。"""

    tenant_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    amount: Decimal = Field(gt=0)


class TicketIn(BaseModel):
    tenant_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=256)
    detail: str = ""


def _rowcount(res: Result[Any]) -> int:
    """DML 的 execute 运行时恒 CursorResult；存根退化为 Result——缝隙单点消化（store.py:193 同款）。"""
    return cast(CursorResult[Any], res).rowcount


async def _load_order(s: AsyncSession, order_id: str, tenant_id: str) -> MockOrderRecord:
    """租户过滤读单（WHERE 第一层；RLS 第二层由调用侧环境承担）；查无 404。"""
    row = (
        await s.execute(
            select(MockOrderRecord).where(MockOrderRecord.id == order_id, MockOrderRecord.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return row


_Executor = Callable[[AsyncSession, "WriteOpIn"], Awaitable[dict[str, Any]]]


async def _claim_and_execute(
    factory: SessionFactory, *, key: str, kind: str, body: WriteOpIn, execute: _Executor
) -> dict[str, Any]:
    """去重算法本体（§4.7 唯一伪代码点的单事务实现）。

    单事务化的两个红利：崩溃零中间态（claim 与结果快照要么同时可见要么都不在）；
    校验失败 HTTPException 上抛→整事务回滚→钥匙不被失败的操作烧掉。
    并发同键：后到者的 INSERT 在唯一索引上等待先到者提交，随后 rowcount=0 走
    回放分支——"恰一次执行"由数据库仲裁，不靠应用层锁。
    """
    async with factory() as s:
        async with s.begin():
            claimed = await s.execute(
                pg_insert(MockWriteOpRecord)
                .values(idempotency_key=key, kind=kind, tenant_id=body.tenant_id, payload={})
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
            )
            if _rowcount(claimed) == 0:
                row = (
                    await s.execute(select(MockWriteOpRecord).where(MockWriteOpRecord.idempotency_key == key))
                ).scalar_one()
                return {"duplicate": True, **row.payload}
            result = await execute(s, body)
            await s.execute(
                update(MockWriteOpRecord).where(MockWriteOpRecord.idempotency_key == key).values(payload=result)
            )
            return {"duplicate": False, **result}


async def _execute_refund(s: AsyncSession, body: WriteOpIn) -> dict[str, Any]:
    """可退性校验 + 执行：状态终态与金额上限两道拒绝面，通过才翻状态。"""
    order = await _load_order(s, body.order_id, body.tenant_id)
    if order.status == MockOrderStatus.REFUNDED.value:
        raise HTTPException(status_code=409, detail="订单已退款，不能重复退款")
    if body.amount > order.paid_amount:
        raise HTTPException(status_code=409, detail=f"退款金额超过可退上限 {order.paid_amount}")
    order.status = MockOrderStatus.REFUNDED.value
    return {"order_id": order.id, "user_id": body.user_id, "amount": str(body.amount), "status": "refunded"}


async def _execute_coupon(s: AsyncSession, body: WriteOpIn) -> dict[str, Any]:
    """补发优惠券：订单存在即发（面额闸门在工具侧 risk_policy——coupon_threshold），不动订单状态。"""
    order = await _load_order(s, body.order_id, body.tenant_id)
    return {"order_id": order.id, "user_id": body.user_id, "amount": str(body.amount), "granted": True}


def create_mock_api(settings: Settings | None = None, session_factory: SessionFactory | None = None) -> FastAPI:
    """mock 子应用工厂（create_app 同款惯例：None=生产缺省，测试传替身）。"""
    s = settings or get_settings()
    factory = session_factory or get_session_factory()
    app = FastAPI(title="Aegis Mock Backend", version="0.1.0")
    app.state.settings = s
    app.state.session_factory = factory
    app.state.tickets = []  # D9：工单台账内存即可（无对抗用例依赖；重启即清是文档声明的取舍）

    @app.middleware("http")
    async def _fault_injection(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        cfg: Settings = request.app.state.settings
        if cfg.mock_latency_ms > 0:
            await asyncio.sleep(cfg.mock_latency_ms / 1000)
        if cfg.mock_error_rate > 0 and random.random() < cfg.mock_error_rate:
            return JSONResponse(status_code=503, content={"detail": "mock 后端注入故障（mock_error_rate）"})
        return await call_next(request)

    @app.get("/orders/{order_id}")
    async def get_order(order_id: str, tenant_id: str, request: Request) -> dict[str, Any]:
        async with request.app.state.session_factory() as db:
            async with db.begin():
                row = await _load_order(db, order_id, tenant_id)
                return {
                    "id": row.id,
                    "tenant_id": row.tenant_id,
                    "user_id": row.user_id,
                    "status": row.status,
                    "paid_amount": str(row.paid_amount),
                    "items": row.items,
                    "created_at": row.created_at.isoformat(),
                }

    @app.get("/logistics/{order_id}")
    async def get_logistics(order_id: str, tenant_id: str, request: Request) -> dict[str, Any]:
        async with request.app.state.session_factory() as db:
            async with db.begin():
                row = await _load_order(db, order_id, tenant_id)
                return {"order_id": row.id, "status": row.status, "track": _TRACKS[row.status]}

    @app.post("/tickets")
    async def post_ticket(body: TicketIn, request: Request) -> dict[str, str]:
        ticket_id = uuid4().hex
        request.app.state.tickets.append({"ticket_id": ticket_id, **body.model_dump(), "status": "open"})
        return {"ticket_id": ticket_id, "status": "open"}

    @app.post("/refunds")
    async def post_refund(
        body: WriteOpIn, request: Request, idempotency_key: Annotated[str | None, Header()] = None
    ) -> dict[str, Any]:
        if not idempotency_key:
            raise HTTPException(status_code=400, detail="缺少 Idempotency-Key 请求头——写操作必须带幂等键")
        return await _claim_and_execute(
            request.app.state.session_factory,
            key=idempotency_key,
            kind="refund",
            body=body,
            execute=_execute_refund,
        )

    @app.post("/coupons")
    async def post_coupon(
        body: WriteOpIn, request: Request, idempotency_key: Annotated[str | None, Header()] = None
    ) -> dict[str, Any]:
        if not idempotency_key:
            raise HTTPException(status_code=400, detail="缺少 Idempotency-Key 请求头——写操作必须带幂等键")
        return await _claim_and_execute(
            request.app.state.session_factory,
            key=idempotency_key,
            kind="coupon",
            body=body,
            execute=_execute_coupon,
        )

    return app

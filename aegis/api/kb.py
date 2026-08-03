"""POST /v1/kb/documents（M3.4 交付④）：知识库文档异步摄取入口——落单即回执。

流程：角色（operator+，02 §7.1 知识库管理归坐席/管理员）→ 落 documents(PENDING,
含原文——偏差(23) 的写入端) → enqueue 投递 (document_id, tenant_id) → 202 回执。
入队走轻量 producer send_task（决策 A）：层契约 api|workers 互不 import——celery
只是三方库，producer 不加载任何任务代码，任务名从 apps 同源常量取（两端一致性
由 ③ 的 wire 测试钉死）。先落库后投递：任务只认 (id, tenant)，行必须先于消息存在
（③ LookupError 的对偶）。投递失败=broker 不可用：503 + 行留 PENDING——
"Redis 挂摄取暂停"是已接受降级（ADR-005 角色4；补投=v2 outbox，00 §10.3）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Annotated, Any
from uuid import uuid4

from celery import Celery
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select

from aegis.api.auth import Principal, require_roles
from aegis.api.ratelimit import rate_limited
from aegis.apps.support.rag.ingest import INGEST_TASK_NAME
from aegis.apps.support.rag.models import DocumentRecord, IngestStatus
from aegis.core.config import Settings
from aegis.core.tenancy import Role, SessionFactory

logger = logging.getLogger(__name__)

router = APIRouter()

_STAFF = require_roles(Role.OPERATOR, Role.ADMIN)

_ADMITTED = rate_limited(_STAFF)
"""M4.2③（观察 ⑥⑭）：kb 上传是花钱通道（一次 202→整链 embedding，200k 字符≈20 万
token），挂租户维度入站限流——与 chat 同桶（inbound:{tenant_id}=租户总入站配额）。
GET 状态查询不挂：读不花钱，与 stream 不挂同理（占连接/纯读归部署面）。"""

EnqueueFn = Callable[[str, str], None]
"""入队缝：(document_id, tenant_id) → 投递。create_app 第六注入参（测试记录假/生产 producer）。"""


class KbDocumentIn(BaseModel):
    source: str = Field(min_length=1, max_length=256)  # 与 documents.source 列宽一致
    text: str = Field(max_length=200_000)  # 演示口径上限；空文本合法（③ 零块 DONE 语义）


def build_enqueue(settings: Settings) -> EnqueueFn:
    """生产入队器：只发不收的 Celery producer。构造零 IO（连接在首次 send 时懒建），
    与 worker 共用同一 broker URL；send_task 是同步 IO——端点侧经 run_in_threadpool
    下放线程池执行，broker 失联的建连超时×重试不再阻塞 event loop（M3 复盘补丁二）。"""
    producer = Celery("aegis", broker=settings.redis_url)

    def enqueue(document_id: str, tenant_id: str) -> None:
        producer.send_task(INGEST_TASK_NAME, args=[document_id, tenant_id])

    return enqueue


@router.post("/v1/kb/documents", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    request: Request,
    principal: Annotated[Principal, Depends(_ADMITTED)],
    body: KbDocumentIn,
) -> dict[str, str]:
    """异步任务回执（202）：document_id 即后续查询句柄；status 恒 pending——
    真进度在 documents.status（PROCESSING/DONE/FAILED 由任务推进）。"""
    doc_id = uuid4().hex
    factory = request.app.state.session_factory
    async with factory() as s:
        async with s.begin():
            s.add(
                DocumentRecord(
                    id=doc_id,
                    tenant_id=principal.tenant_id,  # 身份来自 JWT 不来自载荷——越权写在此关死
                    source=body.source,
                    status=IngestStatus.PENDING.value,
                    text=body.text,
                    meta={},
                )
            )
    try:
        # M3 复盘补丁二：send_task 是同步 IO，直调会阻塞 event loop——成功路径毫秒级，
        # 但 broker 失联时建连超时×重试可达秒级，阻塞的是全进程并发；下放 AnyIO 线程池，
        # 异常仍经 await 原样传回，EnqueueFn 签名与 503 降级分支都不动
        await run_in_threadpool(request.app.state.enqueue, doc_id, principal.tenant_id)
    except Exception as exc:  # broker 不可用（kombu OperationalError 族）：降级不伪装
        logger.warning("摄取入队失败（行留 PENDING，可重投）：document=%s", doc_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="摄取队列不可用，请稍后重试"
        ) from exc
    return {"document_id": doc_id, "status": IngestStatus.PENDING.value}


@router.get("/v1/kb/documents/{document_id}")
async def document_status(
    document_id: str,
    request: Request,
    principal: Annotated[Principal, Depends(_STAFF)],
) -> dict[str, Any]:
    """202 句柄的兑现（M4.2③，观察 ⑱）：三种异常终态（FAILED 死因/卡 PROCESSING/
    永久 PENDING）从此运维可见——error 列是消毒后的死因（M3.4 落列时已打码）。

    staff 面口径与 events_view/trace 同构：owner 缝定位 → 404 缺失 →
    operator 越界 403 点名；admin 平台级。
    """
    lookup: SessionFactory = request.app.state.approvals_lookup  # 平台查读缝（RLS 下 admin 跨租前提）
    async with lookup() as s:
        row = (await s.execute(select(DocumentRecord).where(DocumentRecord.id == document_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    if principal.role is Role.OPERATOR and principal.tenant_id != row.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能查看其他租户的文档")
    return {
        "document_id": row.id,
        "status": row.status,
        "chunk_count": row.chunk_count,
        "error": row.error,
        "source": row.source,
    }

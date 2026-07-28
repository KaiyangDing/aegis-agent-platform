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
from typing import Annotated
from uuid import uuid4

from celery import Celery
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from aegis.api.auth import Principal, require_roles
from aegis.apps.support.rag.ingest import INGEST_TASK_NAME
from aegis.apps.support.rag.models import DocumentRecord, IngestStatus
from aegis.core.config import Settings
from aegis.core.tenancy import Role

logger = logging.getLogger(__name__)

router = APIRouter()

_STAFF = require_roles(Role.OPERATOR, Role.ADMIN)

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
    principal: Annotated[Principal, Depends(_STAFF)],
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

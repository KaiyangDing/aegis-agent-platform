"""M3.4 交付④：POST /v1/kb/documents——落单/回执/入队缝/降级（零 broker：enqueue 记录假）。

状态码分工沿用 chat 的不变量：401 认证 / 403 角色 / 422 载荷 / 503 队列不可用。
入队缝是 create_app 第六注入参（决策 A）：测试注入记录假，两端任务名一致性已由
tests/workers/test_ingest_resume.py 钉死，本文件不重复。
"""

from __future__ import annotations

import threading

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from aegis.api.auth import issue_token
from aegis.api.main import create_app
from aegis.apps.support.rag.models import DocumentRecord, IngestStatus
from aegis.core.config import Settings
from aegis.core.tenancy import Role
from aegis.runtime.runtime import AgentRuntime

SECRET = "kb-test-secret-0123456789abcdef-xyz"  # ≥32B（RFC 7518 下限）


class _NoGateway:
    """kb 测试绝不触发对话——形状占位，误触即炸。"""

    async def complete(self, req):  # pragma: no cover
        raise AssertionError("kb 测试不应触发对话")
        yield


class _RecordingEnqueue:
    """入队缝替身：记录 (document_id, tenant_id) 与执行线程；boom=True 模拟 broker 不可用。"""

    def __init__(self, *, boom: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self.threads: list[int] = []  # 补丁二证词：每次调用发生在哪个线程
        self._boom = boom

    def __call__(self, document_id: str, tenant_id: str) -> None:
        self.threads.append(threading.get_ident())  # 先记后炸：503 路径同样留证
        if self._boom:
            raise ConnectionError("broker 不在")
        self.calls.append((document_id, tenant_id))


def _make_app(factory, enqueue):
    return create_app(
        Settings(jwt_secret=SecretStr(SECRET)),
        session_factory=factory,
        runtime=AgentRuntime(_NoGateway(), factory),
        enqueue=enqueue,
    )


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _bearer(role: Role, uid: str, tid: str = "tenant-a") -> dict[str, str]:
    token = issue_token(user_id=uid, tenant_id=tid, role=role, ttl_s=3600, secret=SECRET)
    return {"Authorization": f"Bearer {token}"}


def _payload(source: str = "faq.md", text: str = "退货政策：七天无理由。") -> dict:
    return {"source": source, "text": text}


async def _doc(factory, doc_id: str) -> DocumentRecord | None:
    async with factory() as s:
        return (await s.execute(select(DocumentRecord).where(DocumentRecord.id == doc_id))).scalar_one_or_none()


@pytest.mark.parametrize(
    ("role", "uid", "expect"),
    [(Role.OPERATOR, "op-a1", 202), (Role.ADMIN, "admin-a1", 202), (Role.USER, "u-a1", 403)],
    ids=["operator", "admin", "user"],
)
async def test_matrix_staff_only(db_session_factory, role, uid, expect) -> None:
    """02 §7.1 矩阵：知识库管理归 operator+/admin；终端用户 403（角色面，非归属面）。"""
    enqueue = _RecordingEnqueue()
    async with _client(_make_app(db_session_factory, enqueue)) as c:
        resp = await c.post("/v1/kb/documents", json=_payload(), headers=_bearer(role, uid))
    assert resp.status_code == expect
    assert (len(enqueue.calls) == 1) is (expect == 202)  # 403 时绝不入队


async def test_upload_persists_pending_and_enqueues(db_session_factory) -> None:
    """202 回执三键一致性：返回 id == 库中行 == 入队参数；租户身份来自 JWT 不来自载荷。"""
    enqueue = _RecordingEnqueue()
    async with _client(_make_app(db_session_factory, enqueue)) as c:
        resp = await c.post(
            "/v1/kb/documents",
            json=_payload(source="退货政策.md", text="七天无理由退货。\n\n生鲜除外。"),
            headers=_bearer(Role.OPERATOR, "op-a1"),
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == IngestStatus.PENDING.value
    doc_id = body["document_id"]
    assert enqueue.calls == [(doc_id, "tenant-a")]
    row = await _doc(db_session_factory, doc_id)
    assert row is not None
    assert (row.tenant_id, row.source, row.status) == ("tenant-a", "退货政策.md", "pending")
    assert row.text == "七天无理由退货。\n\n生鲜除外。"  # 原文落 documents（偏差(23) 的写入端）
    assert row.chunk_count == 0 and row.error is None


async def test_unauthenticated_is_401(db_session_factory) -> None:
    enqueue = _RecordingEnqueue()
    async with _client(_make_app(db_session_factory, enqueue)) as c:
        resp = await c.post("/v1/kb/documents", json=_payload())
    assert resp.status_code == 401
    assert enqueue.calls == []


async def test_enqueue_failure_is_503_and_row_stays_pending(db_session_factory) -> None:
    """broker 不可用=已接受降级（ADR-005 角色4）：503 不假装成功，行留 PENDING 可人工重投。"""
    async with _client(_make_app(db_session_factory, _RecordingEnqueue(boom=True))) as c:
        resp = await c.post(
            "/v1/kb/documents", json=_payload(source="degrade.md"), headers=_bearer(Role.OPERATOR, "op-a1")
        )
    assert resp.status_code == 503
    assert "队列" in resp.json()["detail"]
    async with db_session_factory() as s:
        row = (await s.execute(select(DocumentRecord).where(DocumentRecord.source == "degrade.md"))).scalar_one()
    assert row.status == IngestStatus.PENDING.value  # 先落库后投递：行必须先于消息存在


async def test_payload_validation_is_422(db_session_factory) -> None:
    """载荷面：source 空/缺 text 都是 422——不落库不入队。"""
    enqueue = _RecordingEnqueue()
    async with _client(_make_app(db_session_factory, enqueue)) as c:
        r1 = await c.post("/v1/kb/documents", json={"source": "", "text": "x"}, headers=_bearer(Role.OPERATOR, "op-a1"))
        r2 = await c.post("/v1/kb/documents", json={"source": "a.md"}, headers=_bearer(Role.OPERATOR, "op-a1"))
    assert (r1.status_code, r2.status_code) == (422, 422)
    assert enqueue.calls == []


async def test_enqueue_runs_off_event_loop_thread(db_session_factory) -> None:
    """M3 复盘补丁二回归钉子：同步 enqueue（send_task）必须离开 event loop 线程执行。

    直调的代价只在 broker 失联时显形——建连超时（celery 5.6.3 默认 4s）×重试
    阻塞的是全进程并发；而回退成直调时无任何行为差异可测（照常 202、全绿），
    故以线程身份作证词：执行线程 ≠ 本协程所在的 event loop 线程。
    （ASGITransport 在测试同一 loop 内派发请求，get_ident() 即 loop 线程 id。）
    """
    enqueue = _RecordingEnqueue()
    async with _client(_make_app(db_session_factory, enqueue)) as c:
        resp = await c.post("/v1/kb/documents", json=_payload(), headers=_bearer(Role.OPERATOR, "op-a1"))
    assert resp.status_code == 202
    assert enqueue.threads != []
    assert enqueue.threads[0] != threading.get_ident()

"""M3.12 交付①：四大对抗集中对账面（00 §7.2 毕业验收第 1 条的 CI 承载；零真实调用）。

本文件是毕业**点名面**：四条对抗各自的行为面已由各步测试与真实实录承载——
①`test_retrieval.test_cross_tenant_invisible` + calibrate 字面核证实录／
②`test_cache.test_key_has_tenant_prefix_and_isolates_tenants`（键面机制）／
③`test_tools_ownership` + M3.7 幕 C 实录／④`test_approvals_api.test_operator_cross_tenant_403`
+ demo_hitl 段 B 实录——此处以独立夹具端到端重申，毕业对账指着一个文件念全四条，不追溯散点。

判据出处逐条：①00 §7.2「跨租户检索不可见」②「租户 A 高频问题在 B 侧缓存不命中」
③「水平越权（用户 A 报用户 B 订单号退款）被拒」④「租户 A 坐席审批租户 B 审批单 → 403」。
身份/订单/会话 id 全部随机（M3.10 偏差(52) 硬规则）；SAVEPOINT 夹具=owner 连接绕 RLS，
隔离断言打的是**第一防线**（WHERE / 归属校验 / 端点矩阵），RLS 兜底防线的面在 tests/test_rls.py。
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from pydantic import SecretStr
from sqlalchemy import func, select

from aegis.api.auth import issue_token
from aegis.api.main import create_app
from aegis.apps.support.mock_backend import client as client_mod
from aegis.apps.support.mock_backend.app import create_mock_api
from aegis.apps.support.mock_backend.models import MockOrderRecord, MockWriteOpRecord
from aegis.apps.support.rag.models import EMBEDDING_DIMS, ChunkRecord
from aegis.apps.support.rag.retrieve import Retriever
from aegis.apps.support.tools._shared import DENIED_TEXT
from aegis.apps.support.tools.orders import order_query
from aegis.apps.support.tools.refunds import refund_apply
from aegis.core.config import Settings
from aegis.core.tenancy import Role
from aegis.gateway.cache import ExactCache
from aegis.gateway.schema import LLMChunk, LLMRequest, Message, StopChunk, TextDelta, UsageChunk
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.store import ApprovalRecord, ApprovalStatus, RunState, SessionRecord
from aegis.runtime.tools import ToolContext

_SUF = uuid.uuid4().hex[:8]
SECRET = "adversarial-test-secret-0123456789abcd"  # ≥32B（RFC 7518 下限）


# ---------- 共用小件 ----------


def _vec(axis: int) -> list[float]:
    """单位轴向量（test_retrieval 同款）：同轴 sim=1、异轴 sim=0，余弦可心算。"""
    v = [0.0] * EMBEDDING_DIMS
    v[axis] = 1.0
    return v


class _FixedEmbedder:
    """query 文本 → 预置向量（EmbedderLike 形状替身）。"""

    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self._mapping = mapping

    async def embed(self, texts: Sequence[str], *, tenant_id: str) -> list[list[float]]:
        return [self._mapping[t] for t in texts]


# ---------- 对抗①：跨租户检索不可见 ----------


async def _add_chunk(factory, *, tenant_id: str, text_: str, embedding: list[float]) -> int:
    async with factory() as s:
        async with s.begin():
            rec = ChunkRecord(
                document_id=f"d-adv1-{uuid.uuid4().hex[:8]}",
                tenant_id=tenant_id,
                seq=0,
                text=text_,
                embedding=embedding,
                meta={},
            )
            s.add(rec)
            await s.flush()
            return rec.id


async def test_adv1_cross_tenant_retrieval_returns_empty(db_session_factory) -> None:
    """对抗①本体：B 侧用 A 的语义查询——A 块 WHERE 不可见、B 自家块低于阈值 → 空集拒答。"""
    ten_a, ten_b = f"adv1-a-{_SUF}", f"adv1-b-{_SUF}"
    q = "七天无理由退货政策"
    emb = _FixedEmbedder({q: _vec(0)})
    await _add_chunk(db_session_factory, tenant_id=ten_a, text_="A 专有：七天无理由退货细则", embedding=_vec(0))
    await _add_chunk(db_session_factory, tenant_id=ten_b, text_="B 生鲜配送范围说明", embedding=_vec(1))
    hits = await Retriever(db_session_factory, emb).search(ten_b, q)
    assert list(hits) == []  # 全低于阈值返空（M3.5「宁可说不知道」）——A 内容零出场


async def test_adv1_home_tenant_still_hits(db_session_factory) -> None:
    """对抗①对照正例：同一查询在 A 侧命中自家块——防「全拒也满分」（评测集 normal 同理）。"""
    ten_a = f"adv1-c-{_SUF}"
    q = "退货政策查询"
    emb = _FixedEmbedder({q: _vec(2)})
    cid = await _add_chunk(db_session_factory, tenant_id=ten_a, text_="七天无理由退货细则全文", embedding=_vec(2))
    hits = await Retriever(db_session_factory, emb).search(ten_a, q)
    assert [h.chunk_id for h in hits] == [cid]


# ---------- 对抗②：跨租户缓存不命中 ----------

_CACHE_CHUNKS: list[LLMChunk] = [
    TextDelta(text="缓存的答案"),
    UsageChunk(model="m", prompt_tokens=2, completion_tokens=2),
    StopChunk(reason="end_turn"),
]


def _req(tenant: str, content: str) -> LLMRequest:
    return LLMRequest(tier="fast", tenant_id=tenant, messages=[Message(role="user", content=content)])


class _KeyProbe(ExactCache):
    """只为暴露 _key（test_cache.KeyProbe 同款）：不碰 Redis 的纯键面探针。"""

    def __init__(self) -> None:  # noqa: D107 —— 故意不要 redis 依赖
        self._ttl = 0

    def key(self, r: LLMRequest) -> str:
        return self._key(r)


def test_adv2_cache_key_tenant_prefix() -> None:
    """对抗②键面：同语义请求、不同租户 → key 必不同且租户明文在前缀（可按租户清理）。"""
    probe = _KeyProbe()
    ka, kb = probe.key(_req("adv2-ta", "常见问题")), probe.key(_req("adv2-tb", "常见问题"))
    assert ka != kb
    assert ka.startswith("aegis:cache:v1:adv2-ta:") and kb.startswith("aegis:cache:v1:adv2-tb:")


async def test_adv2_cross_tenant_cache_miss_end_to_end(r) -> None:
    """对抗②端到端（00 §7.2 ② 字面）：A 的高频问题入缓存后，B 同 prompt 取 → miss；A 复取 → hit。"""
    ten_a, ten_b = f"adv2-a-{_SUF}", f"adv2-b-{_SUF}"
    question = f"高频问题-{uuid.uuid4().hex[:8]}"  # 随机化防 db9 残留
    cache = ExactCache(r, ttl_seconds=60)
    await cache.put(_req(ten_a, question), _CACHE_CHUNKS)
    assert await cache.get(_req(ten_b, question)) is None  # B 侧 miss——隔离本体
    assert await cache.get(_req(ten_a, question)) == _CACHE_CHUNKS  # A 侧命中——对照正例


# ---------- 对抗③：水平越权退款被拒 ----------


async def test_adv3_refund_for_others_order_denied(db_session_factory, monkeypatch) -> None:
    """对抗③本体：用户 A 报用户 B 的订单号退款——统一话术拒绝，且台账零写入（拒在任何副作用前）。"""
    ten, owner_uid, attacker_uid = f"adv3-t-{_SUF}", f"u-adv3-own-{_SUF}", f"u-adv3-atk-{_SUF}"
    oid = f"ord-adv3-{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as s:
        async with s.begin():
            s.add(
                MockOrderRecord(
                    id=oid, tenant_id=ten, user_id=owner_uid, status="paid", paid_amount=Decimal("300.00"), items={}
                )
            )
    app = create_mock_api(settings=Settings(), session_factory=db_session_factory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock") as c:
        monkeypatch.setattr(client_mod, "_client", c)
        key = f"adv3-key-{uuid.uuid4().hex[:8]}"
        ctx = ToolContext(
            tenant_id=ten, user_id=attacker_uid, session_id=f"s-adv3-{_SUF}", run_id="r-adv3", tool_call_id=key
        )
        out = await refund_apply.handler(ctx, order_id=oid, amount=50.0)
    assert out == {"error": DENIED_TEXT}
    async with db_session_factory() as s:
        n = (
            await s.execute(
                select(func.count()).select_from(MockWriteOpRecord).where(MockWriteOpRecord.idempotency_key == key)
            )
        ).scalar_one()
    assert n == 0  # 归属校验先于 post_write——越权请求连幂等键都不该消耗


async def test_adv3_cross_tenant_order_read_denied(db_session_factory, monkeypatch) -> None:
    """对抗③跨租户变体（读面）：B 租户用户查 A 租户订单号——同一话术，不泄露存在性。"""
    ten_a, ten_b = f"adv3-a-{_SUF}", f"adv3-b-{_SUF}"
    oid = f"ord-adv3x-{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as s:
        async with s.begin():
            s.add(
                MockOrderRecord(
                    id=oid, tenant_id=ten_a, user_id=f"u-{_SUF}", status="paid", paid_amount=Decimal("100.00"), items={}
                )
            )
    app = create_mock_api(settings=Settings(), session_factory=db_session_factory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock") as c:
        monkeypatch.setattr(client_mod, "_client", c)
        ctx = ToolContext(
            tenant_id=ten_b,
            user_id=f"u-adv3b-{_SUF}",
            session_id=f"s-adv3x-{_SUF}",
            run_id="r",
            tool_call_id=f"k-{_SUF}",
        )
        out = await order_query.handler(ctx, order_id=oid)
    assert out == {"error": DENIED_TEXT}  # 与「订单不存在」逐字节同话术——不泄露他租单号有效性


# ---------- 对抗④：跨租户审批 403 ----------


class _EchoGateway:
    """GatewayLike 最小桩：403 路径根本走不到网关，只为 create_app 组装存在。"""

    async def complete(self, req):
        yield TextDelta(text="好的。")
        yield UsageChunk(model="stub", prompt_tokens=1, completion_tokens=1)
        yield StopChunk(reason="end_turn")


class _Limiter:
    async def try_take(self, scope, rate, capacity, cost=1.0):
        return (True, 0.0)


async def test_adv4_cross_tenant_approval_403(db_session_factory) -> None:
    """对抗④（00 §7.2 ④ 字面）：B 租户坐席批 A 租户审批单 → 403，单据保持 pending 未被消费。"""
    ten_a, ten_b = f"adv4-a-{_SUF}", f"adv4-b-{_SUF}"
    sid = f"s-adv4-{uuid.uuid4().hex[:8]}"
    aid = f"ap-{sid}"
    async with db_session_factory() as s:
        async with s.begin():
            s.add(
                SessionRecord(id=sid, tenant_id=ten_a, user_id=f"u-{_SUF}", run_state=RunState.AWAITING_APPROVAL.value)
            )
            s.add(
                ApprovalRecord(
                    id=aid,
                    session_id=sid,
                    tenant_id=ten_a,
                    tool_name="refund_apply",
                    args={"order_id": "x", "amount": 300},
                    status=ApprovalStatus.PENDING.value,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
    app = create_app(
        Settings(jwt_secret=SecretStr(SECRET)),
        session_factory=db_session_factory,
        runtime=AgentRuntime(_EchoGateway(), db_session_factory),  # 403 在 decide 之前，恢复入口不可达
        limiter=_Limiter(),
        gateway=_EchoGateway(),
        approvals_lookup=db_session_factory,
    )
    token = issue_token(user_id=f"op-{_SUF}", tenant_id=ten_b, role=Role.OPERATOR, ttl_s=3600, secret=SECRET)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            f"/v1/approvals/{aid}", json={"decision": "approve"}, headers={"Authorization": f"Bearer {token}"}
        )
    assert resp.status_code == 403
    async with db_session_factory() as s:
        row = (await s.execute(select(ApprovalRecord).where(ApprovalRecord.id == aid))).scalar_one()
    assert row.status == ApprovalStatus.PENDING.value  # 越权请求对单据零影响

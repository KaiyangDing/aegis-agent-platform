"""HITL 审批的 worker 侧（M3.9 交付④，plans 14i 拍板Ⅴ/Ⅵ）：真实恢复钩子 + 审批对账扫描。

两件事共用一套任务局部装配（_task_runtime）：worker 每任务 asyncio.run 新建
event loop，进程级三单例（get_redis/get_engine/shared_client）与 mock 通路都绑
创建时的 loop——全部换成任务局部实例，经 build_gateway/build_session_lock 参数化
缝与 set_mock_client 安装缝注入（M3.4 build_embedding_client 双参数化同款）。
身份纪律：扫描与读身份走 owner 引擎（D4 维护面）；恢复本体在 tenant_context(租户)
内走 app 引擎+guard（M3.4 决策 B 的对偶——恢复是替租户续做业务，不是平台维护）。
对账扫描（拍板Ⅵ）：expire_due 批量翻转后不依赖其返回值，而是扫"awaiting 会话 ×
最新审批单已决"全集逐单踢 resume(approval_id)——翻转与消费之间的崩溃窗
（W0/取消端点同款）由每轮扫描自愈，不留永久孤儿。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aegis.apps.support.agent import build_agent_spec
from aegis.apps.support.mock_backend.app import create_mock_api
from aegis.apps.support.mock_backend.client import set_mock_client
from aegis.apps.support.rag.retrieve import RetrievalProvider, Retriever
from aegis.apps.support.revalidate import build_precheck
from aegis.core.config import get_settings
from aegis.core.locks import build_session_lock
from aegis.core.redis import new_redis_client
from aegis.core.tenancy import SessionFactory, TenantRecord
from aegis.core.tenant_ctx import install_tenant_guard, tenant_context
from aegis.gateway.factory import build_embedding_client, build_gateway
from aegis.gateway.providers.base import new_http_client
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.store import ApprovalRecord, ApprovalStatus, ApprovalStore, RunState, SessionRecord
from aegis.workers.celery_app import celery_app
from aegis.workers.reaper import register_resume_hook

logger = logging.getLogger(__name__)

KickHook = Callable[[str, str], Awaitable[None]]
"""对账扫描的恢复出口：(session_id, approval_id)。生产=_kick（任务局部装配踢恢复）；
测试注入 spy——sweep_once 与 reap_once 同款：调度逻辑直测零 broker 零真实装配。"""


_SWEEP_LIMIT = 100
"""单轮扫描批上限（M4.2③，观察 (61)；list_expired limit=100 先例）：worker 停摆重启后
N 最大的时刻恰是最该干活的时刻——分批 + 每轮从状态重推 = 自愈不塌；一轮 1+2N 个
引擎会话的工作量从此有界。触顶必留痕（silent cap 纪律），余量下一轮 beat 继续。"""


@dataclass(frozen=True, slots=True)
class SweepReport:
    """一轮对账的账目：expired=本轮翻转的到期单 / waiting=本批 awaiting 会话数
    （≤_SWEEP_LIMIT）/ kicked=被踢恢复的 (session_id, approval_id) /
    failed=踢失败的同形对（M4.2③：单单隔离不再静默吞账）。"""

    expired: tuple[str, ...]
    waiting: int
    kicked: tuple[tuple[str, str], ...]
    failed: tuple[tuple[str, str], ...] = ()


async def sweep_once(factory: SessionFactory, *, kick: KickHook, now: datetime | None = None) -> SweepReport:
    """审批对账一轮（owner 面）：翻转到期单 + 扫"awaiting × 最新单已决"踢恢复。

    "最新单"判据：同会话审批单在生产中由不同事务先后创建（created_at 可序）；
    最新单 pending=正常等待不动；最新单已决（approved/rejected/cancelled/expired）
    而会话仍 awaiting=决案与续跑之间崩过（W0）——resume(approval_id) 四结局分诊
    现成（实况块 #7），与并发消费者的赛跑由 T3 CAS 裁出恰一赢家。
    绝不按旧单踢：旧 EXPIRED+新 PENDING（新审批周期）时踢旧单会经 T3 掐掉
    正在等新单的 run。单单隔离（reap_once P6 同款）：一单炸不中断整批。
    """
    expired = tuple(await ApprovalStore(factory).expire_due(now=now))
    if expired:
        logger.info("审批到期翻转 %d 单", len(expired))
    async with factory() as s:
        waiting = (
            (
                await s.execute(
                    select(SessionRecord.id)
                    .where(SessionRecord.run_state == RunState.AWAITING_APPROVAL.value)
                    .order_by(SessionRecord.id)  # LIMIT 无序=每轮随机领批；定序让余量必然轮到
                    .limit(_SWEEP_LIMIT)
                )
            )
            .scalars()
            .all()
        )
    if len(waiting) == _SWEEP_LIMIT:
        logger.warning("对账扫描达批上限 %d，余量下轮继续", _SWEEP_LIMIT)
    kicked: list[tuple[str, str]] = []
    failed: list[tuple[str, str]] = []
    for sid in waiting:
        async with factory() as s:
            latest = (
                await s.execute(
                    select(ApprovalRecord)
                    .where(ApprovalRecord.session_id == sid)
                    .order_by(ApprovalRecord.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if latest is None:
            # awaiting 会话零审批单=不可能态（挂起必先开单）：留痕不代管（M4.2③，(61)）
            logger.warning("awaiting 会话无任何审批单（不可能态，留观不代管）：session=%s", sid)
            continue
        if latest.status == ApprovalStatus.PENDING.value:
            continue  # 正常等待中
        try:
            await kick(sid, latest.id)
            kicked.append((sid, latest.id))
        except Exception:
            logger.exception("对账恢复失败（单单隔离）：session=%s approval=%s", sid, latest.id)
            failed.append((sid, latest.id))
    return SweepReport(expired=expired, waiting=len(waiting), kicked=tuple(kicked), failed=tuple(failed))


async def _tenant_of_session(session_id: str) -> TenantRecord:
    """owner 视角读身份与租户行（D4 维护面：判断与装配是平台职能，不冒充租户）。"""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as s:
            tenant_id = (
                await s.execute(select(SessionRecord.tenant_id).where(SessionRecord.id == session_id))
            ).scalar_one_or_none()
            if tenant_id is None:
                raise RuntimeError(f"会话 {session_id} 不存在——无从装配恢复现场")
            tenant = (await s.execute(select(TenantRecord).where(TenantRecord.id == tenant_id))).scalar_one_or_none()
        if tenant is None:
            raise RuntimeError(f"租户 {tenant_id} 无行（种子缺失）——无法装配 AgentSpec")
        return tenant
    finally:
        await engine.dispose()


@asynccontextmanager
async def _task_runtime() -> AsyncIterator[AgentRuntime]:
    """任务局部 AgentRuntime：本任务的 event loop 里现建、finally 全量归还。

    与 create_app 生产缺省链逐件对应（gateway/lock/retrieval/precheck），差异只在
    资源来源：进程单例 → 任务局部实例。app 引擎连 database_url_app+guard（RLS
    冒充租户的物质基础，值由外层 tenant_context 提供）；mock 通路经 set_mock_client
    安装（工具面只认 mock_client() 单点——--pool=solo 串行是前提；容器 prefork
    每子进程独立同样成立）。

    **对应关系是人肉承诺+本声明，机制上区分不了"有意不加"与"忘了加"（M4.7 (64)
    显式登记）**——已知的两条有意差异：⑴ 无 msg_redis/_TokenEmitter → worker 驱动
    的续跑不写 msgbuf，用户断线重连期间收不到 message_reset（GET 侧看到整段一次性
    出现，与 API 驱动逐 token 推送实时性不对称）；⑵ 无 text_sink（它本就是每请求物
    而非装配参数——站 11 更正）。create_app 侧改装配件时，此清单必须同步核对。
    """
    settings = get_settings()
    app_engine = create_async_engine(settings.database_url_app, poolclass=NullPool)
    install_tenant_guard(app_engine)
    app_factory = async_sessionmaker(app_engine, expire_on_commit=False)
    redis = new_redis_client()
    http = new_http_client()
    mock = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_mock_api(settings, app_factory)), base_url="http://mock-backend"
    )
    set_mock_client(mock)
    try:
        retrieval = RetrievalProvider(Retriever(app_factory, build_embedding_client(app_factory, http)))
        runtime = AgentRuntime(
            build_gateway(session_factory=app_factory, redis=redis, client=http),
            app_factory,
            lock=build_session_lock(redis=redis, engine=app_engine),
            precheck=build_precheck(app_factory),
            retrieval=retrieval,
        )
        yield runtime
    finally:
        # M4.0②（63）：五件串行释放各自保护——一件抛不该带走其余（长驻 worker 每任务
        # 泄漏一条 HTTP 池/Redis 连接/DB 引擎，累积成"跑一天后打不开新连接"），且清理
        # 期的次生异常不该顶掉 try 体内真正的首因（M2.12 偏差 #7 同族）。
        # 释放顺序不变：先摘装配缝，再由外向内还资源。
        set_mock_client(None)
        for _name, _close in (
            ("mock", mock.aclose),
            ("http", http.aclose),
            ("redis", redis.aclose),
            ("engine", app_engine.dispose),
        ):
            try:
                await _close()
            except Exception:
                logger.warning("任务局部资源释放失败（继续释放其余）：%s", _name, exc_info=True)


async def _resume_in_context(session_id: str, approval_id: str | None) -> None:
    """装配 spec + 任务局部 runtime，调恢复单入口。approval_id=None=崩溃分诊
    （#44 审批认领在 L2 a+ 支内——钩子保持薄）；非 None=审批四结局分诊。
    事件已由 runtime 落盘，这里只消费不转发（worker 无对外流）。"""
    tenant = await _tenant_of_session(session_id)
    spec = build_agent_spec(tenant)
    with tenant_context(tenant.id):
        async with _task_runtime() as runtime:
            async for _event in runtime.resume(spec, session_id, approval_id=approval_id):
                pass


async def resume_session(session_id: str, lease_owner: str, lease_generation: int) -> None:
    """真实恢复钩子（ResumeHook 形状，reaper.py:38）。(lease_owner, generation) 是
    steal 的凭据快照：runtime 内部以同 owner 重入续接（store.py acquire 同 owner
    分支——steal→钩子→resume 的同进程交接），此处仅留痕。"""
    logger.info("崩溃恢复认领：session=%s（steal owner=%s gen=%d）", session_id, lease_owner, lease_generation)
    await _resume_in_context(session_id, None)


async def _kick(session_id: str, approval_id: str) -> None:
    """对账出口的生产实现：按单踢恢复单入口（approved 执行/拒绝族终止，四结局分诊）。"""
    await _resume_in_context(session_id, approval_id)


async def _sweep_fresh() -> SweepReport:
    """同步壳的 async 内胆：owner NullPool 引擎，finally 归还（reaper 3.2#8 同款）。"""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        return await sweep_once(factory, kick=_kick)
    finally:
        await engine.dispose()


@celery_app.task(name="aegis.workers.hitl.expire_approvals")
def expire_approvals() -> dict[str, int]:
    """beat 周期任务薄同步壳（reaper 3.2#7 同款）：asyncio.run 包 async 内核。"""
    report = asyncio.run(_sweep_fresh())
    logger.info(
        "审批对账完成：expired=%d waiting=%d kicked=%d failed=%d",
        len(report.expired),
        report.waiting,
        len(report.kicked),
        len(report.failed),
    )
    return {
        "expired": len(report.expired),
        "waiting": report.waiting,
        "kicked": len(report.kicked),
        "failed": len(report.failed),
    }


# 进程级注册真实恢复钩子（拍板Ⅰ收尾）：celery include 点名本模块=worker 启动即注册；
# API 进程按层契约（api | workers 互不 import）不加载本模块，注册不外溢。
# 测试需要干净态时 register_resume_hook(None) 复位（reaper.py:47）。
register_resume_hook(resume_session)

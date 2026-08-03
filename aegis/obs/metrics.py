"""Prometheus 指标面（M4.2 交付①，00 §8.1）：自有 registry + 双源架构。

双源（m4 计划 §3-1）：
- 进程内观测（Counter/Histogram）：只覆盖 api 层看得见的东西——HTTP 计数、
  chat 首 token/全程延迟；打点全在 api 层（M4.2② 接线），runtime/gateway
  永不 import obs（层契约反向本就非法，双源架构让它也没有理由）。
- scrape 时 DB 派生（Gauge）：token/成本/工具/终止/转人工/缓存/预算/文档——
  事实源就是账本与事件表（"events 即 trace 源"同哲学），/metrics 前刷新现算。
DB 派生 Gauge 是跨进程重启单调的累计值（HELP 均声明 cumulative）；比率一律
不预计算——导出原始计数，比率在 PromQL 查询侧算（转人工率=#8/#4）。
刷新必须走平台维护面（owner 工厂，D4）：/metrics 无认证无租户身份，app 工厂的
RLS 世界里 sessions/usage_ledger/tenants/documents 全是空集且零报错——(58) 家族
第三例，这次埋在计划伪码里（"refresh(get_session_factory())"是错的）。
钱的精确面在账本（Decimal 字符串出线，M3.1 契约）；指标值是 float64 观测近似，
两者分工不冲突。失败哲学：任何一族刷新失败=跳过该族+日志留痕、保留上次值，
绝不把异常抛给 scrape（监控自己把服务拖垮=双倍事故）。
认证口径（M4.2 拍板 1）：v1 无认证；防线=端口全程只绑 127.0.0.1（00 §2.2
安全底线）；生产形态应内网隔离或加 basic auth——02 §7.1 已补行。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aegis.core.tenancy import SessionFactory
from aegis.gateway.metering import MeteringRecorder

logger = logging.getLogger(__name__)

REGISTRY = CollectorRegistry()
"""自有 registry：躲开 prometheus-client 全局默认表的重复注册炸点（pytest 反复
import 的经典事故）；族只在本模块顶层声明恰一次，/metrics 用 generate_latest(REGISTRY)。"""

# ---- 进程内观测（api 层打点，M4.2② 接线）----
HTTP_REQUESTS = Counter(
    "aegis_http_requests",
    "HTTP 请求计数（api 中间件；path 为路由模板防 label 基数爆炸）",
    ["path", "method", "status"],
    registry=REGISTRY,
)
CHAT_FIRST_TOKEN_S = Histogram(
    "aegis_chat_first_token_seconds",
    "chat 首 token 延迟：t0=进入 handler，观测点=首个 token 帧（M3.12/M5.2 同口径）",
    ["tenant_id"],
    registry=REGISTRY,
    buckets=(0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 2.5, 5.0, 10.0, 30.0),  # 2.5 桶界=M3 验收阈值
)
CHAT_REQUEST_S = Histogram(
    "aegis_chat_request_seconds",
    "chat 全程延迟（首帧到流尽）",
    ["tenant_id"],
    registry=REGISTRY,
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0),
)

# ---- scrape 时 DB 派生（cumulative, safe for rate()）----
RUNS_TERMINATED = Gauge(
    "aegis_runs_terminated",
    "run 终止计数，按终止原因分维（cumulative, safe for rate()；成功率=completed/合计）",
    ["tenant_id", "reason"],
    registry=REGISTRY,
)
LLM_TOKENS = Gauge(
    "aegis_llm_tokens",
    "账本 token 累计（cumulative；kind=prompt|completion）",
    ["tenant_id", "tier", "kind"],
    registry=REGISTRY,
)
LLM_COST_YUAN = Gauge(
    "aegis_llm_cost_yuan",
    "账本成本累计（元，cumulative；精确金额以 usage_ledger Decimal 为准，此处为观测近似）",
    ["tenant_id"],
    registry=REGISTRY,
)
TOOL_INVOCATIONS = Gauge(
    "aegis_tool_invocations",
    "工具调用计数，按终局分维（cumulative；工具成功率=succeeded/合计）",
    ["tool_name", "status"],
    registry=REGISTRY,
)
HANDOFFS = Gauge(
    "aegis_handoffs",
    "转人工计数（cumulative；转人工率分母用 aegis_runs_terminated 合计）",
    ["tenant_id"],
    registry=REGISTRY,
)
CACHE_REQUESTS = Gauge(
    "aegis_cache_requests",
    "LLM 调用按缓存结果分维（cumulative；命中率=hit/(hit+miss)）",
    ["result"],
    registry=REGISTRY,
)
TENANT_BUDGET_USED_RATIO = Gauge(
    "aegis_tenant_budget_used_ratio",
    "本月 token 用量/月度预算（#23 逼近告警最小形态；budget≤0 的租户不导出）",
    ["tenant_id"],
    registry=REGISTRY,
)
DOCUMENTS = Gauge(
    "aegis_documents",
    "知识库文档按摄取状态计数（FAILED/PROCESSING 的运维可见面）",
    ["tenant_id", "status"],
    registry=REGISTRY,
)

# ---- 派生查询（报表聚合用裸 SQL——00 §2.2 数据访问口径）----
_TERMINATED_SQL = text(
    "SELECT s.tenant_id AS tenant_id, e.payload->>'reason' AS reason, count(*) AS n "
    "FROM events e JOIN sessions s ON s.id = e.session_id "  # events 无 tenant_id 列（P5）
    "WHERE e.type = 'loop_terminated' GROUP BY 1, 2"
)
_TOKENS_SQL = text(
    "SELECT tenant_id, tier, coalesce(sum(prompt_tokens), 0) AS p, coalesce(sum(completion_tokens), 0) AS c "
    "FROM usage_ledger GROUP BY 1, 2"
)
_COST_SQL = text("SELECT tenant_id, coalesce(sum(cost), 0) AS cost FROM usage_ledger GROUP BY 1")
_TOOLS_SQL = text("SELECT tool_name, status, count(*) AS n FROM tool_invocations GROUP BY 1, 2")
_HANDOFFS_SQL = text(
    "SELECT s.tenant_id AS tenant_id, count(*) AS n "
    "FROM events e JOIN sessions s ON s.id = e.session_id WHERE e.type = 'handoff' GROUP BY 1"
)
_CACHE_SQL = text("SELECT cached, count(*) AS n FROM usage_ledger GROUP BY 1")
_DOCS_SQL = text("SELECT tenant_id, status, count(*) AS n FROM documents GROUP BY 1, 2")
_BUDGET_TENANTS_SQL = text("SELECT id, token_budget_monthly FROM tenants WHERE token_budget_monthly > 0")


def _apply_terminated(r: Any) -> None:
    RUNS_TERMINATED.labels(tenant_id=r.tenant_id, reason=r.reason or "unknown").set(r.n)


def _apply_tokens(r: Any) -> None:
    LLM_TOKENS.labels(tenant_id=r.tenant_id, tier=r.tier, kind="prompt").set(r.p)
    LLM_TOKENS.labels(tenant_id=r.tenant_id, tier=r.tier, kind="completion").set(r.c)


def _apply_cost(r: Any) -> None:
    LLM_COST_YUAN.labels(tenant_id=r.tenant_id).set(float(r.cost))


def _apply_tools(r: Any) -> None:
    TOOL_INVOCATIONS.labels(tool_name=r.tool_name, status=r.status).set(r.n)


def _apply_handoffs(r: Any) -> None:
    HANDOFFS.labels(tenant_id=r.tenant_id).set(r.n)


def _apply_cache(r: Any) -> None:
    CACHE_REQUESTS.labels(result="hit" if r.cached else "miss").set(r.n)


def _apply_docs(r: Any) -> None:
    DOCUMENTS.labels(tenant_id=r.tenant_id, status=r.status).set(r.n)


_SIMPLE_FAMILIES: tuple[tuple[str, Any, Callable[[Any], None]], ...] = (
    ("aegis_runs_terminated", _TERMINATED_SQL, _apply_terminated),
    ("aegis_llm_tokens", _TOKENS_SQL, _apply_tokens),
    ("aegis_llm_cost_yuan", _COST_SQL, _apply_cost),
    ("aegis_tool_invocations", _TOOLS_SQL, _apply_tools),
    ("aegis_handoffs", _HANDOFFS_SQL, _apply_handoffs),
    ("aegis_cache_requests", _CACHE_SQL, _apply_cache),
    ("aegis_documents", _DOCS_SQL, _apply_docs),
)


async def refresh_db_metrics(factory: SessionFactory) -> None:
    """scrape 前刷新全部 DB 派生族。factory 必须是平台维护面（owner，D4）——见模块头。

    族间隔离：一族失败=该族跳过（保留上次值）+ 一行警告，其余照刷；
    任何情况下不向调用方抛异常（/metrics 的 fail-safe 由此成立）。
    """
    for name, sql, apply in _SIMPLE_FAMILIES:
        try:
            async with factory() as s:
                rows = (await s.execute(sql)).all()
            for r in rows:
                apply(r)
        except Exception:
            logger.warning("指标族刷新失败（保留上次值）：%s", name, exc_info=True)
    try:
        # #23 预算比：分子复用月度闸门同一实现（MeteringRecorder.month_spend——同一把尺，
        # 告警与拦截永不对不上）；month_spend 不触价目表，空表构造即可（形状相容 cast）
        meter = MeteringRecorder(cast("async_sessionmaker[AsyncSession]", factory), {})
        async with factory() as s:
            tenants = (await s.execute(_BUDGET_TENANTS_SQL)).all()
        for row in tenants:
            spent = await meter.month_spend(row.id)
            TENANT_BUDGET_USED_RATIO.labels(tenant_id=row.id).set(spent / row.token_budget_monthly)
    except Exception:
        logger.warning("指标族刷新失败（保留上次值）：aegis_tenant_budget_used_ratio", exc_info=True)


def render() -> tuple[bytes, str]:
    """导出 exposition 文本：(正文, Content-Type)。"""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST

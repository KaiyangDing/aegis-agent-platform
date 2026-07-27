"""M3.11 交付③：L3 cassette 冒烟——载入合格 + 能被 FakeGateway 回放（M4.3 主体回归的前哨）。

资产依赖测试的诚实形态：cassette 未录制时 skip 并指路（本地录制前）；资产入库后
CI 必在、不 skip（PG/Redis「无则 skip、CI 必在」同款惯例）。
回放重绑定随机会话（M2.11 偏差 #14 惯用法：frozen dataclass 重构 session_id——
本机 dev 库有录制时已提交的同名会话行，复用原 id 会撞 sessions_pkey 且 seq 接续旧流）；
spec 与台词经 importlib 取自录制脚本模块常量（I1 单一事实源，行为断言主体归 M4.3）。
"""

from __future__ import annotations

import importlib.util
import re
import sys
import uuid
from functools import lru_cache
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from aegis.apps.support.agent import build_agent_spec
from aegis.apps.support.mock_backend import client as client_mod
from aegis.apps.support.mock_backend.app import create_mock_api
from aegis.core.config import Settings
from aegis.runtime.events import EventType
from aegis.runtime.replay import Cassette, FakeGateway
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import TerminationReason
from aegis.runtime.store import SessionRecord

ROOT = Path(__file__).resolve().parents[2]
L3_DIR = ROOT / "tests" / "cassettes" / "l3"
_SCRIPT_PATH = ROOT / "scripts" / "record_l3_cassettes.py"


@lru_cache(maxsize=1)
def _script() -> ModuleType:
    """装载录制脚本（import 期零副作用：main() 有 __main__ 门、关缓存 env 在 main 内设）。"""
    spec = importlib.util.spec_from_file_location("record_l3_cassettes", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # 必须先注册再执行：future-annotations 模块里的 @dataclass 反解字符串注解时
    # 会查 sys.modules[cls.__module__]，未注册得 None 当场 AttributeError——
    # M2.11 惯用法的隐藏前提（record_long_dialog 无模块级 dataclass 才侥幸未踩）
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load(name: str) -> Cassette:
    path = L3_DIR / _script().CASSETTE_FILES[name]
    if not path.exists():
        pytest.skip(f"L3 cassette 未录制：先跑 uv run python scripts/record_l3_cassettes.py（缺 {path.name}）")
    return Cassette.load(path)


async def _make_session(factory, sid: str, *, tenant_id: str, user_id: str) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=sid, tenant_id=tenant_id, user_id=user_id))


def test_l3_cassettes_wellformed_and_clean() -> None:
    """五盘载入合格 + 各盘 main 道条目数落在设计形状 + 资产级扫密（红线双保险）。"""
    script = _script()
    lanes: dict[str, int] = {}
    for name, filename in script.CASSETTE_FILES.items():
        c = _load(name)
        assert c.session_id, f"{filename} session_id 空"
        lanes[name] = len(c.scopes.get("main", ()))
        text = (L3_DIR / filename).read_text(encoding="utf-8")
        assert re.search(r"sk-[A-Za-z0-9_-]{8,}", text) is None, f"{filename} 含 sk- 模式"
    assert lanes["budget_token_exceeded"] == 0, "预算盘应零条目（闸门 #3 预检在调用前）"
    assert lanes["hitl_approve_resume"] >= 2, "HITL 盘应含挂起段+续跑段至少两次调用"
    for name in ("isolation_cross_tenant_rag", "isolation_cross_user_refund", "tool_roundtrip_order_query"):
        assert lanes[name] >= 1, f"{name} main 道为空"


async def test_budget_cassette_replays_token_budget_exceeded(db_session_factory) -> None:
    """预算盘端到端回放：同 spec（I1 同源构造）同台词 → 预检同点触发，零网关消费。"""
    script = _script()
    recorded = _load("budget_token_exceeded")
    sid = f"l3-replay-budget-{uuid.uuid4().hex[:8]}"
    cassette = Cassette(session_id=sid, scopes=recorded.scopes)
    await _make_session(db_session_factory, sid, tenant_id="tenant-a", user_id="u-a1")
    fake = FakeGateway(cassette)
    runtime = AgentRuntime(fake, db_session_factory)
    spec = build_agent_spec(
        script.tenant_from_seed(script.load_seed(), "tenant-a", session_token_budget=script.BUDGET_TOKEN_LIMIT)
    )
    reasons = [
        ev.payload["reason"]
        async for ev in runtime.run(spec, sid, script.PROMPT_BUDGET)
        if ev.type is EventType.LOOP_TERMINATED
    ]
    assert reasons == [TerminationReason.TOKEN_BUDGET_EXCEEDED.value]
    fake.assert_exhausted()  # 空盘放空=确定性闭环：录了多少放多少


async def test_tool_roundtrip_cassette_replays_full_chain(db_session_factory, monkeypatch) -> None:
    """工具盘全链回放：FakeGateway 扮演 LLM、mock 后端真执行——工具序列与终止原因逐点复现。

    订单经 seed_demo.seed_orders upsert（幂等，本机撞已提交种子行走 update、CI 裸库走 insert）；
    mock 子应用重建在测试工厂上（wired_mock 先例）。
    """
    script = _script()
    seed = script.load_seed()
    recorded = _load("tool_roundtrip_order_query")
    await seed.seed_orders(db_session_factory, orders=[o for o in seed.ORDERS if o["id"] == "AZ-1001"])
    sid = f"l3-replay-tool-{uuid.uuid4().hex[:8]}"
    cassette = Cassette(session_id=sid, scopes=recorded.scopes)
    await _make_session(db_session_factory, sid, tenant_id="tenant-a", user_id="u-a1")
    app = create_mock_api(settings=Settings(), session_factory=db_session_factory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock") as c:
        monkeypatch.setattr(client_mod, "_client", c)
        fake = FakeGateway(cassette)
        runtime = AgentRuntime(fake, db_session_factory)
        spec = build_agent_spec(script.tenant_from_seed(seed, "tenant-a"))
        reasons: list[str] = []
        tool_calls: list[str] = []
        async for ev in runtime.run(spec, sid, script.PROMPT_TOOL):
            if ev.type is EventType.LOOP_TERMINATED:
                reasons.append(ev.payload["reason"])
            elif ev.type is EventType.TOOL_CALL:
                tool_calls.append(ev.payload["tool_name"])
    assert reasons == [TerminationReason.COMPLETED.value]
    assert tool_calls and set(tool_calls) == {"order_query"}
    fake.assert_exhausted()

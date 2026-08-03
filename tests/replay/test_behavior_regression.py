"""M4.3 交付①：CI 回放行为回归——终止原因/工具序列/隔离预算三类断言（00 §8.1 M4.3 行）。

回放测**行为**、真实调用测**质量**，双流水线不可互替（03 §7 / 04 M4）：本文件断言
"同一 cassette 在当前代码管线下重现出同一条行为轨迹"，不断言回答文本逐字相等
（重录后必漂，那是噪声不是回归信号）。期望值先于断言从用例设计推导（README §6
登记表"覆盖"列 + 录制脚本自检判据），不抄实际输出——抄输出是快照，坏行为会被
固化成"期望"（plans/m4 §3-6）。断言字面量一律经 TerminationReason/EventType 枚举
构造：typo 在构造期炸，不静默漂过。装置住本模块不进 conftest（m2.6 测试样式；
且无包结构下测试模块无法可靠 import conftest——M3.9"模块名全仓唯一"同族约束）。

三族 cassette 三种装配，消费同一份 manifest（expectations.json）：
- M2 手写盘（minimal_demo + adversarial×4）——演示工具集世界。spec/台词与
  tests/runtime 既有测试逐字同源：工具集经 importlib 复装 tests/runtime/conftest.py，
  不复刻第二份定义（handler 返回值参与 forbidden 扫描面，第二份定义漂移即假绿/假红）；
- M2.11 长对话盘——SPEC/TURNS 经 importlib 取自录制脚本（I1，benchmark 同款）；
- M3.11 L3 五盘——spec 从种子常量构造（录制回放定义性同源），按盘挂配：
  mock 后端（ASGITransport 进程内直调 + monkeypatch 进程单例，冒烟同款）、
  审批动作（decide→resume，录制脚本 act_hitl 同款）、预算注入（BUDGET_TOKEN_LIMIT）。

四条装置纪律：
1. 一律重绑定随机 session_id（M2.11 偏差 #14：真实录制类资产的原 id 在本机 dev 库
   有已提交残留，复用即撞 pkey 且 seq 接续旧流；手写盘无此患，统一重绑定让代码只有一条路）；
2. 事件从事实源全量读（M2.12 _db_events 同款）——decide 落的 approval_decided
   不经 run/resume 产出流，只有 DB 面才是完整行为轨迹；
3. 回放世界不配 retrieval：录制期检索空集（B 查 A 专有 = 阈值拒答）→ builder 装填零块，
   回放不注入 provider 得到等价上下文形态（匹配键不含 prompt 哈希）；检索质量不在
   回放被测面，归校准脚本与 M4.4 评测；
4. assert_exhausted 默认全盘开启（录了没放完 = 行为轨迹变短，也是漂移，D14）；
   豁免两盘各有语义理由，见 EXHAUSTED_EXEMPT。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from collections.abc import Awaitable, Callable
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from aegis.apps.support.agent import build_agent_spec
from aegis.apps.support.mock_backend import client as client_mod
from aegis.apps.support.mock_backend.app import create_mock_api
from aegis.apps.support.revalidate import build_precheck
from aegis.core.config import Settings
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.replay import Cassette, FakeGateway, normalize_events
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec, LoopPolicy, TerminationReason
from aegis.runtime.store import ApprovalStore, EventRecord, SessionRecord
from aegis.runtime.tools import ToolRegistry

ROOT = Path(__file__).resolve().parents[2]
CASSETTE_DIR = ROOT / "tests" / "cassettes"
MANIFEST_PATH = Path(__file__).resolve().parent / "expectations.json"

# ---------------------------------------------------------------- manifest 面

# manifest key = 相对 tests/cassettes/ 的 POSIX 路径（如 "l3/budget_token_exceeded.json"）。
MANIFEST: dict[str, dict[str, Any]] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _cassettes_on_disk() -> set[str]:
    """盘面清单（POSIX 相对路径）：完整性测试的另一半。README 不是 cassette，rglob 不会碰它。"""
    return {p.relative_to(CASSETTE_DIR).as_posix() for p in CASSETTE_DIR.rglob("*.json")}


# ---------------------------------------------------------------- 装载器


def _load_module(alias: str, path: Path) -> ModuleType:
    """importlib 装载非包脚本（项目惯用法）：先注册 sys.modules 再执行——
    future-annotations 模块含 dataclass 时反解字符串注解要查 sys.modules（M3.11 教训⑵）。"""
    spec = importlib.util.spec_from_file_location(alias, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _demo_toolbox() -> ModuleType:
    """复装 tests/runtime/conftest.py 取演示工具三件（同定义不复刻）。

    pytest 以自有插件机制装载该 conftest，本处 importlib 实例与之独立、别名不撞；
    模块顶层只有 @tool 包装与 fixture 定义，import 期零副作用，双装安全。"""
    return _load_module("replay_demo_toolbox", ROOT / "tests" / "runtime" / "conftest.py")


@lru_cache(maxsize=1)
def _long_script() -> ModuleType:
    return _load_module("replay_record_long_dialog", ROOT / "scripts" / "record_long_dialog.py")


@lru_cache(maxsize=1)
def _l3_script() -> ModuleType:
    return _load_module("replay_record_l3", ROOT / "scripts" / "record_l3_cassettes.py")


# ---------------------------------------------------------------- 装配件


def _load_cassette(key: str) -> Cassette:
    return Cassette.load(CASSETTE_DIR / key)


def _sid(key: str) -> str:
    return f"replay-{Path(key).stem}-{uuid.uuid4().hex[:8]}"


async def _make_session(factory: Any, sid: str, *, tenant_id: str, user_id: str) -> None:
    async with factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=sid, tenant_id=tenant_id, user_id=user_id))


async def _db_events(factory: Any, session_id: str) -> list[AgentEvent]:
    """从事实源读全序列（M2.12 同款）：run/resume 产出 ∪ decide 审计写入。"""
    async with factory() as s:
        rows = (
            (await s.execute(select(EventRecord).where(EventRecord.session_id == session_id).order_by(EventRecord.seq)))
            .scalars()
            .all()
        )
    return [
        AgentEvent(
            id=r.id, session_id=r.session_id, run_id=r.run_id, seq=r.seq, type=EventType(r.type), payload=r.payload
        )
        for r in rows
    ]


def _demo_spec(*, with_tools: bool, policy: LoopPolicy | None = None) -> AgentSpec:
    """M2 族 spec：与 tests/runtime/test_loop_adversarial.py 的构造逐字一致。"""
    kwargs: dict[str, Any] = {"system_prompt": "你是演示客服。"}
    if with_tools:
        m = _demo_toolbox()
        kwargs["tools"] = ToolRegistry([m.demo_order_query, m.demo_refund_apply, m.demo_ticket_create]).specs()
    if policy is not None:
        kwargs["policy"] = policy
    return AgentSpec(**kwargs)


# ---------------------------------------------------------------- 驱动族

Driver = Callable[[Any, pytest.MonkeyPatch], Awaitable[tuple[str, FakeGateway]]]
"""盘驱动：装配并跑完该盘对应的会话，返回 (session_id, gateway)——事件由 _replay 统一从 DB 读。"""


def _m2_driver(
    key: str, turns: tuple[str, ...], *, with_tools: bool = True, policy: LoopPolicy | None = None
) -> Driver:
    async def drive(factory: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[str, FakeGateway]:
        recorded = _load_cassette(key)
        sid = _sid(key)
        cassette = Cassette(session_id=sid, scopes=recorded.scopes)
        await _make_session(factory, sid, tenant_id="t-a", user_id="u-1")
        fake = FakeGateway(cassette)
        runtime = AgentRuntime(fake, factory)
        spec = _demo_spec(with_tools=with_tools, policy=policy)
        for text in turns:
            async for _ in runtime.run(spec, sid, text):
                pass
        return sid, fake

    return drive


async def _drive_long_dialog(factory: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[str, FakeGateway]:
    script = _long_script()
    recorded = _load_cassette("long_dialog.json")
    sid = _sid("long_dialog.json")
    cassette = Cassette(session_id=sid, scopes=recorded.scopes)
    await _make_session(factory, sid, tenant_id="bench", user_id="bench-user")
    fake = FakeGateway(cassette)
    runtime = AgentRuntime(fake, factory)
    for text in script.TURNS:
        async for _ in runtime.run(script.SPEC, sid, text):
            pass
    return sid, fake


def _l3_run_driver(
    key: str,
    *,
    tenant_id: str,
    user_id: str,
    prompt_attr: str,
    seed_order_ids: tuple[str, ...] = (),
    with_mock: bool = False,
    budget_from_script: bool = False,
) -> Driver:
    """L3 单 run 族（iso_rag / iso_refund / budget / tool）：冒烟测试同款装配。"""

    async def drive(factory: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[str, FakeGateway]:
        script = _l3_script()
        seed = script.load_seed()
        recorded = _load_cassette(key)
        sid = _sid(key)
        cassette = Cassette(session_id=sid, scopes=recorded.scopes)
        if seed_order_ids:
            await seed.seed_orders(factory, orders=[o for o in seed.ORDERS if o["id"] in seed_order_ids])
        await _make_session(factory, sid, tenant_id=tenant_id, user_id=user_id)
        overrides: dict[str, object] = {}
        if budget_from_script:
            overrides["session_token_budget"] = script.BUDGET_TOKEN_LIMIT
        spec = build_agent_spec(script.tenant_from_seed(seed, tenant_id, **overrides))
        fake = FakeGateway(cassette)
        runtime = AgentRuntime(fake, factory)
        prompt = getattr(script, prompt_attr)
        if with_mock:
            app = create_mock_api(settings=Settings(), session_factory=factory)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock") as c:
                monkeypatch.setattr(client_mod, "_client", c)
                async for _ in runtime.run(spec, sid, prompt):
                    pass
        else:
            async for _ in runtime.run(spec, sid, prompt):
                pass
        return sid, fake

    return drive


async def _drive_hitl(factory: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[str, FakeGateway]:
    """HITL 盘：run 挂起（无终止事件）→ decide 批准 → resume 续跑（录制脚本 act_hitl 同款）。

    precheck 与录制期同构注入（build_precheck）——批准后前置校验在回放面同样在岗；
    挂起段"恰一张审批单"是装置前提（录制自检钉过），破了在这里响亮炸而不是静默跑偏。"""
    script = _l3_script()
    seed = script.load_seed()
    recorded = _load_cassette("l3/hitl_approve_resume.json")
    sid = _sid("l3/hitl_approve_resume.json")
    cassette = Cassette(session_id=sid, scopes=recorded.scopes)
    await seed.seed_orders(factory, orders=[o for o in seed.ORDERS if o["id"] == "AZ-1002"])
    await _make_session(factory, sid, tenant_id="tenant-a", user_id="u-a1")
    spec = build_agent_spec(script.tenant_from_seed(seed, "tenant-a"))
    fake = FakeGateway(cassette)
    runtime = AgentRuntime(fake, factory, precheck=build_precheck(factory))
    app = create_mock_api(settings=Settings(), session_factory=factory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock") as c:
        monkeypatch.setattr(client_mod, "_client", c)
        approval_ids = [
            ev.payload["approval_id"]
            async for ev in runtime.run(spec, sid, script.PROMPT_HITL)
            if ev.type is EventType.APPROVAL_REQUESTED
        ]
        assert len(approval_ids) == 1, f"挂起段应恰一张审批单，得到 {approval_ids}"
        decided = await ApprovalStore(factory).decide(approval_ids[0], approved=True, operator_id="op-a1")
        assert decided, "decide CAS 失败——单据不是 pending"
        async for _ in runtime.resume(spec, sid, approval_ids[0]):
            pass
    return sid, fake


DRIVERS: dict[str, Driver] = {
    "minimal_demo.json": _m2_driver(
        "minimal_demo.json", ("订单 A-1001 发货了吗？", "帮我再查一次 A-1001 的状态和金额")
    ),
    "adversarial_tool_loop.json": _m2_driver("adversarial_tool_loop.json", ("查订单 A-13",)),
    "adversarial_empty_replies.json": _m2_driver("adversarial_empty_replies.json", ("在吗",), with_tools=False),
    "adversarial_runaway_iterations.json": _m2_driver(
        "adversarial_runaway_iterations.json", ("把这些订单全部核对一遍",)
    ),
    "adversarial_token_burn.json": _m2_driver(
        "adversarial_token_burn.json", ("把这些都处理掉",), policy=LoopPolicy(session_token_budget=2_000)
    ),
    "long_dialog.json": _drive_long_dialog,
    "l3/isolation_cross_tenant_rag.json": _l3_run_driver(
        "l3/isolation_cross_tenant_rag.json", tenant_id="tenant-b", user_id="u-b1", prompt_attr="PROMPT_ISO_RAG"
    ),
    "l3/isolation_cross_user_refund.json": _l3_run_driver(
        "l3/isolation_cross_user_refund.json",
        tenant_id="tenant-a",
        user_id="u-a1",
        prompt_attr="PROMPT_ISO_REFUND",
        seed_order_ids=("AZ-2001",),
        with_mock=True,
    ),
    "l3/budget_token_exceeded.json": _l3_run_driver(
        "l3/budget_token_exceeded.json",
        tenant_id="tenant-a",
        user_id="u-a1",
        prompt_attr="PROMPT_BUDGET",
        budget_from_script=True,
    ),
    "l3/hitl_approve_resume.json": _drive_hitl,
    "l3/tool_roundtrip_order_query.json": _l3_run_driver(
        "l3/tool_roundtrip_order_query.json",
        tenant_id="tenant-a",
        user_id="u-a1",
        prompt_attr="PROMPT_TOOL",
        seed_order_ids=("AZ-1001",),
        with_mock=True,
    ),
}

EXHAUSTED_EXEMPT: dict[str, str] = {
    "adversarial_token_burn.json": "剩余条目=被预算闸门拦下的意图本身（既有测试同款：故意不 assert_exhausted）",
    "minimal_demo.json": "summary 道 1 条为 M2.6 格式演示保留，两轮短对话不触发滚动摘要",
}
"""耗尽断言豁免名单：键必须 ∈ DRIVERS（完整性测试钉死），理由随键落档。"""


async def _replay(key: str, factory: Any, monkeypatch: pytest.MonkeyPatch) -> list[AgentEvent]:
    """回放一盘：驱动 → 耗尽核对 → 返回事实源全量事件序列。"""
    sid, fake = await DRIVERS[key](factory, monkeypatch)
    if key not in EXHAUSTED_EXEMPT:
        fake.assert_exhausted()
    return await _db_events(factory, sid)


# ---------------------------------------------------------------- 断言件


def _last_termination_reason(events: list[AgentEvent]) -> str:
    terminated = [e for e in events if e.type is EventType.LOOP_TERMINATED]
    assert terminated, "事件流里没有 loop_terminated——回放没跑到任何终局"
    return str(terminated[-1].payload["reason"])


def _extract_tool_sequence(events: list[AgentEvent]) -> list[tuple[str, str]]:
    """[(tool_name, "ok"|"error"), …] 按事件流序。

    tool_result/tool_error payload 不带工具名（executor.py:213/310 实况），经
    payload["tool_call_id"] 关联回 tool_call 事件（write-ahead：事件 id 即幂等键）；
    引用流外调用 = 装置或管线 bug，KeyError 响亮红，不兜底（C10 精神）。"""
    names = {e.id: str(e.payload["tool_name"]) for e in events if e.type is EventType.TOOL_CALL}
    sequence: list[tuple[str, str]] = []
    for e in events:
        if e.type is EventType.TOOL_RESULT:
            sequence.append((names[e.payload["tool_call_id"]], "ok"))
        elif e.type is EventType.TOOL_ERROR:
            sequence.append((names[e.payload["tool_call_id"]], "error"))
    return sequence


_MECHANICAL_KEYS = frozenset({"iteration", "input_tokens_est", "digest"})
"""forbidden 扫描面的机械噪声键（payload 顶层）：前两键=run 簿记（M2.12 剔除面同款），
digest=内容哈希 hex——64 字符十六进制串撞"259"这类数字禁词的概率非零且逐盘恒定，
留着等于让隔离断言的红绿取决于哈希巧合。语义内容（result 原文、话术）不受影响。"""


def _dump_text(events: list[AgentEvent]) -> str:
    """forbidden_output 的扫描面：C31 归一化（豁免 usage/latency 等墙钟数字域、
    id 别名化抹掉 uuid hex）后再剔机械噪声键，剩下的就是语义文本域。"""
    normalized = normalize_events(events)
    for item in normalized:
        for key in _MECHANICAL_KEYS:
            item["payload"].pop(key, None)
    return json.dumps(normalized, ensure_ascii=False)


# ---------------------------------------------------------------- 测试


def test_every_cassette_has_expectation() -> None:
    """完整性（三向双检）：盘面 ≡ manifest ≡ 驱动注册；豁免名单不许挂空键。

    双向集合相等而非子集：新录了盘没挂期望（漏检面扩大）与期望悬空（盘被删改名）
    都是红——弱模型漏挂 manifest 的第一道防线（§3-1 选 manifest 不选 sidecar 的理由）。"""
    on_disk = _cassettes_on_disk()
    assert on_disk == set(MANIFEST), (
        f"盘面与 manifest 不一致：盘面多出 {on_disk - set(MANIFEST)}，manifest 悬空 {set(MANIFEST) - on_disk}"
    )
    assert set(MANIFEST) == set(DRIVERS), (
        f"manifest 与驱动注册不一致：缺驱动 {set(MANIFEST) - set(DRIVERS)}，驱动悬空 {set(DRIVERS) - set(MANIFEST)}"
    )
    assert set(EXHAUSTED_EXEMPT) <= set(DRIVERS), "耗尽豁免名单挂了不存在的盘"


def test_manifest_keys_are_posix() -> None:
    """manifest key 统一 POSIX 斜杠：Windows 反斜杠在 CI（Linux）对不上盘面文件（§7-4）。"""
    offenders = [k for k in MANIFEST if "\\" in k]
    assert not offenders, f"manifest key 含反斜杠：{offenders}"


def _event(event_id: str, event_type: EventType, payload: dict[str, Any]) -> AgentEvent:
    # seq=1 恒定：AgentEvent 构造校验 seq≥1（events.py:70）；装置自检不比对相对序，同值无妨
    return AgentEvent(id=event_id, session_id="unit", run_id="r1", seq=1, type=event_type, payload=payload)


def test_extract_tool_sequence_unit() -> None:
    """装置自检：ok/error 二分经 tool_call_id 关联回名字；引用流外调用响亮 KeyError 不兜底（C10）。"""
    events = [
        _event("c1", EventType.TOOL_CALL, {"tool_name": "alpha"}),
        _event("e2", EventType.TOOL_RESULT, {"tool_call_id": "c1", "result": {}}),
        _event("c2", EventType.TOOL_CALL, {"tool_name": "beta"}),
        _event("e4", EventType.TOOL_ERROR, {"tool_call_id": "c2", "error": "boom"}),
    ]
    assert _extract_tool_sequence(events) == [("alpha", "ok"), ("beta", "error")]
    ghost = [_event("e9", EventType.TOOL_RESULT, {"tool_call_id": "ghost", "result": {}})]
    with pytest.raises(KeyError):
        _extract_tool_sequence(ghost)


def test_dump_text_strips_mechanical_noise() -> None:
    """装置自检：机械噪声（哈希 hex/估算簿记）不进 forbidden 扫描面，语义内容保留。

    没有这一剔除，"259" 这类数字禁词的红绿会取决于 digest 哈希是否恰好含该三字符
    ——隔离断言不许押注在巧合上。剔除只滴 payload 顶层（D12）：result 原文里的
    同名业务字段与语义文本原样保留，禁词真出现在语义域时照样红。"""
    noise = _event("e1", EventType.TOOL_RESULT, {"tool_call_id": "e1", "digest": "ab259cd", "input_tokens_est": 1259})
    assert "259" not in _dump_text([noise])
    semantic = _event("e1", EventType.TOOL_RESULT, {"tool_call_id": "e1", "result": {"note": "实付 259 元"}})
    assert "259" in _dump_text([semantic])


@pytest.mark.parametrize("key", sorted(MANIFEST))
async def test_behavior_trace(key: str, db_session_factory: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """行为轨迹回归主体（每盘一例）：终止原因必断；工具序列/禁词/必现事件按 manifest 键在场断言。

    键缺省=该维度不断言（如 token_burn 的工具序列绑估算尺 C25 的触发细节，钉死会让
    合法调参恒红，信噪比差——终止原因已锁住"预算先于轮数"这一行为本体）。"""
    exp = MANIFEST[key]
    events = await _replay(key, db_session_factory, monkeypatch)

    expected_reason = TerminationReason(exp["termination_reason"])  # typo 在构造期炸
    assert _last_termination_reason(events) == expected_reason.value

    if "tool_sequence" in exp:
        expected_seq = [(name, outcome) for name, outcome in exp["tool_sequence"]]
        assert _extract_tool_sequence(events) == expected_seq

    if exp.get("forbidden_output"):
        text = _dump_text(events)
        banned_hits = [b for b in exp["forbidden_output"] if b in text]
        assert not banned_hits, f"隔离硬约束被穿：事件流语义域出现禁词 {banned_hits}"

    for etype in exp.get("required_event_types", []):
        wanted = EventType(etype)  # typo 在构造期炸
        assert any(e.type is wanted for e in events), f"必现事件缺席：{etype}"

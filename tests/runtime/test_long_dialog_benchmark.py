"""M2.11 交付③：长对话基准回放验收——真实录制 cassette 的 CI 承载（00 §6.2 第 4 条）。

全部回放驱动零真实调用（00 §6.0；CI 无 DASHSCOPE_API_KEY 恰好复证）。判据与录制自检
是同一套（I1）：TURNS/SPEC/PROBES/normalized/check_recall 经 importlib 从录制脚本装载，
剧本与断言单一事实源、不抄第二份。

关键词断言局限（D7，面试口径）：只验"归一化后字符串在场"不验语义正确，误报由埋点
高熵性质压制（D6）；回放不重跑模型——断言钉住的是"录制当时真实模型在滚动摘要压缩后
答对了"这一凭证 + "回放可精确重建该轨迹"；后续改坏上下文管线时，回归信号来自道内
序号失配响亮报错（C10），不是关键词变化。语义级召回评测归 M4.4，不在本文件扩权。
"""

from __future__ import annotations

import importlib.util
import re
import uuid
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from aegis.core.config import Settings
from aegis.runtime.events import AgentEvent, EventType
from aegis.runtime.replay import Cassette, FakeGateway
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import TerminationReason

ROOT = Path(__file__).resolve().parents[2]
CASSETTE_PATH = ROOT / "tests" / "cassettes" / "long_dialog.json"
README_PATH = ROOT / "tests" / "cassettes" / "README.md"
_SCRIPT_PATH = ROOT / "scripts" / "record_long_dialog.py"


@lru_cache(maxsize=1)
def _script() -> ModuleType:
    """经 importlib 装载录制脚本（缓存）：剧本与判据的单一事实源（I1）。

    脚本 import 期零副作用已核实（Settings 惰性构造、main() 有 __main__ 门——
    plans/m2.11 偏差 #5）：装载不落盘、不调网络、不读 key。
    """
    spec = importlib.util.spec_from_file_location("record_long_dialog", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _cassette() -> Cassette:
    """模块级装载缓存（m2.6 测试样式：共用道具不进 conftest）；资产只读。"""
    return Cassette.load(CASSETTE_PATH)


async def _replay_all(factory, make_session) -> tuple[dict[int, str], list[AgentEvent]]:
    """把 cassette 重绑定到随机新会话后重跑全部 40 轮，返回（轮号→assistant 终稿, 全事件）。

    为什么不用 cassette 头部的原 session_id（plans/m2.11 偏差 #14，M2.10 残留教训变体）：
    真实录制往本机 dev 库**提交过**该会话的 sessions/events 行——测试事务只回滚自己的
    写入，挡不住已提交的残留，复用原 id 会撞 sessions_pkey 且 seq 接续旧流（CI 库干净
    反而全绿=环境依赖测试）。D10 的真正目的仅是"请求与带子的匹配键一致"——重绑定
    session_id（frozen dataclass 重新构造）完整保全它，回放从此不依赖机器状态。
    sessions 行建在测试事务内（外层回滚吞掉）；FakeGateway 每次新实例——游标是消费
    进度，跨用例共享实例即错配之源；收尾断言四道全部耗尽：录了没放完 = 行为轨迹
    变短，也是漂移（D14）。
    """
    script = _script()
    recorded = _cassette()
    session_id = f"replay-long-dialog-{uuid.uuid4().hex[:8]}"
    cassette = Cassette(session_id=session_id, scopes=recorded.scopes)
    await make_session(session_id, tenant_id="bench", user_id="bench-user")
    gateway = FakeGateway(cassette)
    runtime = AgentRuntime(gateway, factory)
    transcript: dict[int, str] = {}
    events: list[AgentEvent] = []
    for i, user_input in enumerate(script.TURNS, 1):
        async for ev in runtime.run(script.SPEC, session_id, user_input):
            events.append(ev)
            if ev.type is EventType.ASSISTANT_MESSAGE:
                transcript[i] = ev.payload["content"]  # 终态覆盖：同轮多条取最后（与脚本同口径）
    gateway.assert_exhausted()
    return transcript, events


def test_cassette_exists_and_wellformed() -> None:
    """资产在位且合格：M2.6 格式可载入、头部 session_id 非空、main 道条目数落 [30, 45]。

    区间防"夹具被缩水/膨胀"静默漂移：40 轮无工具 = main 道恰 40 条 ± 结构余量，
    30 是 00 §11 砍法下限（长对话夹具 40 轮缩 30 轮）。
    """
    c = _cassette()
    assert c.session_id
    assert 30 <= len(c.scopes["main"]) <= 45


def test_cassette_contains_no_secret_material() -> None:
    """资产级扫密（红线双保险之二；之一=录制期 request_digest 不落 prompt 原文 + 落盘前扫密）。

    sk- 模式对齐 base.py 消毒口径；本地配了真 key 时再比一道明文（CI 无 key，该半步自然空转）。
    """
    text = CASSETTE_PATH.read_text(encoding="utf-8")
    assert re.search(r"sk-[A-Za-z0-9_-]{8,}", text) is None
    key = Settings().dashscope_api_key.get_secret_value()  # 干净实例，不动 get_settings 单例缓存
    if key:
        assert key not in text


async def test_replay_triggers_at_least_two_rolling_summaries(db_session_factory, make_session) -> None:
    """00 §6.2 第 4 条前半：回放重跑 40 轮，滚动摘要 >=2（实录 2 次，第 23/31 轮触发）。"""
    _, events = await _replay_all(db_session_factory, make_session)
    assert sum(1 for e in events if e.type is EventType.SUMMARY_UPDATED) >= 2


async def test_last_summary_covers_planted_turns(db_session_factory, make_session) -> None:
    """末次摘要覆盖含第 PROBE_COVER_TURN=12 轮——探针答的是压缩链路，不是原文窗口（陷阱 10）。

    12 = 末个字面埋点/复述轮：配合"12 轮后用户台词零字面埋点值"的剧本纪律，覆盖 >=12
    保证此后一切埋点值提及（含助手自发复读）都只能派生自摘要链（plans/m2.11 偏差 #7）。
    """
    script = _script()
    _, events = await _replay_all(db_session_factory, make_session)
    summaries = [e for e in events if e.type is EventType.SUMMARY_UPDATED]
    assert summaries, "回放未产生任何 summary_updated——资产或管线已漂移"
    assert summaries[-1].payload["turn_to"] >= script.PROBE_COVER_TURN


async def test_planted_facts_recalled_after_compression(db_session_factory, make_session) -> None:
    """00 §6.2 第 4 条后半：五埋点压缩后全召回——判据=脚本同款 check_recall（I1 同一套的第二次执行）。

    归一化=两侧剔 [-\\s] + 全角冒号折半角（确定性排版折叠）；语义级改写仍判失败（D7 局限）。
    """
    script = _script()
    transcript, _ = await _replay_all(db_session_factory, make_session)
    assert script.check_recall(transcript) == []


async def test_every_turn_terminates_completed(db_session_factory, make_session) -> None:
    """不变量 I4 的 CI 镜像：40 轮各恰一次 loop_terminated 且原因全为 completed。"""
    script = _script()
    _, events = await _replay_all(db_session_factory, make_session)
    reasons = [e.payload["reason"] for e in events if e.type is EventType.LOOP_TERMINATED]
    assert reasons == [TerminationReason.COMPLETED.value] * len(script.TURNS)


async def test_summary_calls_recorded_on_summary_scope(db_session_factory, make_session) -> None:
    """C10 四道分计数在真实资产上的结构性证据：summary 道条目 >=2 且与回放摘要事件数一致。

    配合 _replay_all 的 assert_exhausted：道内条目与触发点一一对应——录制期任何
    "触发→失败→无痕"（C34 fail-open）都会在此错位暴露（plans/m2.11 偏差 #8 的回放侧镜像）。
    """
    _, events = await _replay_all(db_session_factory, make_session)
    recorded = len(_cassette().scopes["summary"])
    produced = sum(1 for e in events if e.type is EventType.SUMMARY_UPDATED)
    assert recorded >= 2
    assert recorded == produced


def test_registry_lists_every_termination_reason() -> None:
    """登记表与枚举防漂移：README 登记表含全部 8 个终止原因值——枚举新增成员时本测试先红。"""
    text = README_PATH.read_text(encoding="utf-8")
    for reason in TerminationReason:
        assert reason.value in text, f"基准会话集登记表缺终止原因 {reason.value}"

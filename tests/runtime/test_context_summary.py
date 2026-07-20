"""M2.5 交付②：会话历史层 + 滚动摘要（plans/m2.5 §4.3、§5.2）。

分轮口径 = 2026-07-11 拍板项 1（user 起、同轮最后一条 assistant 终态止、孤儿轮独立）；
触发公式 = need > prewarm_ratio × budget_h（拍板项 2，默认 0.8）；摘要在 build 内
同步确定点执行（拍板项 3）；失败 fail-open + logger 留痕（拍板项 4/C34）。
零真实调用（00 §6.0）：summarize 全为假钩子。

造数口径：轮次内容用 CJK 精控 token（tokens.py：CJK 1 字 1 token）——
_u/_a 各 15 token，一轮 30；history_budget=101、user_input="问"（1 token）
⇒ budget_h=100、触发线 80。
"""

from __future__ import annotations

from sqlalchemy import select

from aegis.core.tokens import estimate_tokens
from aegis.runtime.context import _CLIP_SUFFIX, _SUMMARY_HEADER, ContextBuilder, _message_tokens
from aegis.runtime.events import EventType
from aegis.runtime.spec import ContextConfig
from aegis.runtime.store import EventRecord, EventWriter, SessionRecord


def _u(i: int) -> str:
    """第 i 轮 user 原文：15 token（CJK 14 + 单位数字 ≈1）。"""
    return f"问{i}" + "长" * 13


def _a(i: int) -> str:
    """第 i 轮 assistant 原文：15 token。"""
    return f"答{i}" + "长" * 13


async def _seed_session(factory, sid: str) -> None:
    """先建会话行：summary_updated 投影是 UPDATE，无行必炸 ProjectionError（store.py:261）。"""
    async with factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=sid, tenant_id="t-ctx", user_id="u-ctx"))


async def _seed_turns(factory, sid: str, n: int, *, run_id: str = "r-old", start: int = 1) -> None:
    """以旧 run 写入 n 对 user/assistant 事件（经真投影落 messages 表）。"""
    w = await EventWriter.open(factory, sid, run_id)
    for i in range(start, start + n):
        await w.append(EventType.USER_MESSAGE, {"content": _u(i)})
        await w.append(EventType.ASSISTANT_MESSAGE, {"content": _a(i)})


class _Hook:
    """计数假摘要钩子：记录每次收到的 source（D8 格式断言用）。"""

    def __init__(self, result: str = "摘" * 5) -> None:
        self.calls: list[str] = []
        self._result = result

    async def __call__(self, text: str) -> str:
        self.calls.append(text)
        return self._result


async def _make(factory, sid: str, *, run_id: str = "r-cur", **kw) -> tuple[ContextBuilder, EventWriter]:
    """开当前 run 的写入器 + builder（默认 history_budget=101）。"""
    w = await EventWriter.open(factory, sid, run_id)
    b = ContextBuilder(
        factory,
        w,
        config=ContextConfig(history_budget=101),
        tenant_id="t-ctx",
        user_id="u-ctx",
        **kw,
    )
    return b, w


async def _summary_events(factory, sid: str) -> list[dict]:
    """按 seq 序取全部 summary_updated 事件的 payload。"""
    async with factory() as s:
        rows = (
            await s.execute(
                select(EventRecord.payload)
                .where(EventRecord.session_id == sid, EventRecord.type == "summary_updated")
                .order_by(EventRecord.seq)
            )
        ).scalars()
        return list(rows)


async def test_turns_grouped_from_projection(db_session_factory) -> None:
    """拍板项 1：n 对消息 ⇒ n 轮、轮号从 1 递增、原文与 token 入轮。"""
    await _seed_turns(db_session_factory, "cs-1", 3)
    b, _ = await _make(db_session_factory, "cs-1")
    turns = await b._load_turns()
    assert [t.index for t in turns] == [1, 2, 3]
    assert turns[0].user == _u(1)
    assert turns[0].assistant == _a(1)
    assert turns[2].tokens == estimate_tokens(_u(3)) + estimate_tokens(_a(3))


async def test_orphan_user_counts_as_turn(db_session_factory) -> None:
    """孤儿 user（上次 run 崩溃遗留）独立成轮、assistant 为空——用户说过的话不许蒸发。"""
    w = await EventWriter.open(db_session_factory, "cs-2", "r-old")
    await w.append(EventType.USER_MESSAGE, {"content": _u(1)})
    await w.append(EventType.ASSISTANT_MESSAGE, {"content": _a(1)})
    await w.append(EventType.USER_MESSAGE, {"content": _u(2)})  # 孤儿：无 assistant 即遇下一条 user
    await w.append(EventType.USER_MESSAGE, {"content": _u(3)})
    await w.append(EventType.ASSISTANT_MESSAGE, {"content": _a(3)})
    b, _ = await _make(db_session_factory, "cs-2")
    turns = await b._load_turns()
    assert [(t.index, t.assistant == "") for t in turns] == [(1, False), (2, True), (3, False)]
    assert turns[1].user == _u(2)


async def test_history_excludes_current_run(db_session_factory) -> None:
    """D4：当前 run 已落盘的 user_message 不进历史层——防与 user_input 参数重复注入。"""
    await _seed_turns(db_session_factory, "cs-3", 1)
    b, w = await _make(db_session_factory, "cs-3")
    await w.append(EventType.USER_MESSAGE, {"content": "当前问题"})  # M2.7"每步先写事件"的时序
    out = await b.build(system_prompt="规则", user_input="当前问题")
    assert sum(1 for m in out if m.role == "user" and m.content == "当前问题") == 1
    assert any(m.content == _u(1) for m in out)  # 旧 run 的轮照常在


async def test_under_threshold_no_summarize(db_session_factory) -> None:
    """阈值之下（need=60 ≤ 80）：钩子零调用、零事件、两轮原文全量在场（拍板项 2）。"""
    await _seed_turns(db_session_factory, "cs-4", 2)
    hook = _Hook()
    b, _ = await _make(db_session_factory, "cs-4", summarize=hook)
    out = await b.build(system_prompt="规则", user_input="问")
    assert hook.calls == []
    assert await _summary_events(db_session_factory, "cs-4") == []
    contents = [m.content for m in out]
    assert _u(1) in contents
    assert _a(2) in contents


async def test_trigger_compresses_oldest_half(db_session_factory) -> None:
    """命中阈值（120>80）：恰一次调用、压最老一半（D9）、payload 三键（D7）、source 为 D8 格式。"""
    await _seed_session(db_session_factory, "cs-5")
    await _seed_turns(db_session_factory, "cs-5", 4)
    hook = _Hook()
    b, _ = await _make(db_session_factory, "cs-5", summarize=hook)
    out = await b.build(system_prompt="规则", user_input="问")
    assert len(hook.calls) == 1
    source = hook.calls[0]
    assert source.startswith(f"第 1 轮\n用户：{_u(1)}\n助手：{_a(1)}\n")  # D8 拼接格式，进 cassette 后钉死
    assert _u(2) in source
    assert _u(3) not in source  # 只压最老 k=ceil(4/2)=2 轮
    assert await _summary_events(db_session_factory, "cs-5") == [{"summary": "摘" * 5, "turn_from": 1, "turn_to": 2}]
    summary_msg = next(m for m in out if m.content.startswith(_SUMMARY_HEADER.format(turn_from=1, turn_to=2)))
    assert summary_msg.role == "system"
    contents = [m.content for m in out]
    assert _u(3) in contents
    assert _u(4) in contents  # 未覆盖轮原文照放
    assert _u(1) not in contents  # 被压缩轮退出 prompt（events 原文仍在，另测钉死）


async def test_summary_projection_updated_same_tx(db_session_factory) -> None:
    """C8：summary_updated 写入后 sessions.summary 已是新摘要（M2.2 投影同事务派生）。"""
    await _seed_session(db_session_factory, "cs-6")
    await _seed_turns(db_session_factory, "cs-6", 4)
    b, _ = await _make(db_session_factory, "cs-6", summarize=_Hook("售后已解决"))
    await b.build(system_prompt="规则", user_input="问")
    async with db_session_factory() as s:
        row = await s.get(SessionRecord, "cs-6")
    assert row is not None
    assert row.summary == "售后已解决"


async def test_second_trigger_extends_coverage(db_session_factory) -> None:
    """I6：覆盖游标单调推进、新摘要输入含旧摘要（滚动=累积）——M2.11"≥2 次滚动摘要"的单测前身。"""
    await _seed_session(db_session_factory, "cs-7")
    await _seed_turns(db_session_factory, "cs-7", 4)
    b1, _ = await _make(db_session_factory, "cs-7", run_id="r-cur1", summarize=_Hook())
    await b1.build(system_prompt="规则", user_input="问")
    await _seed_turns(db_session_factory, "cs-7", 2, run_id="r-old2", start=5)  # 再灌两轮
    hook2 = _Hook("新摘" * 3)
    b2, _ = await _make(db_session_factory, "cs-7", run_id="r-cur2", summarize=hook2)
    await b2.build(system_prompt="规则", user_input="问")
    assert hook2.calls[0].startswith("摘" * 5 + "\n")  # 旧摘要是新摘要输入的前缀
    payloads = await _summary_events(db_session_factory, "cs-7")
    assert [p["turn_to"] for p in payloads] == [2, 4]  # 单调递增：2 → 2+ceil(4/2)
    assert payloads[1]["summary"] == "新摘" * 3


async def test_summarize_failure_fails_open(db_session_factory) -> None:
    """C34/拍板项 4：钩子 raise ⇒ 零事件、确定性丢最老轮、历史层仍 ≤ 预算；build 不掀翻。"""

    async def boom(text: str) -> str:
        raise RuntimeError("fast 档摘要挂了")

    await _seed_turns(db_session_factory, "cs-8", 4)
    b, _ = await _make(db_session_factory, "cs-8", summarize=boom)
    out = await b.build(system_prompt="规则", user_input="问")
    assert await _summary_events(db_session_factory, "cs-8") == []
    contents = [m.content for m in out]
    assert _u(1) not in contents  # 最老轮被整轮丢弃（D10）
    assert _a(1) not in contents
    assert _u(2) in contents
    assert _a(4) in contents
    assert sum(_message_tokens(m) for m in out[1:-1]) <= 100  # I7：历史层 ≤ budget_h


async def test_no_summarizer_drops_oldest_turns(db_session_factory) -> None:
    """无钩子超预算 ⇒ 与摘要失败共用同一确定性兜底（D10）。"""
    await _seed_turns(db_session_factory, "cs-9", 4)
    b, _ = await _make(db_session_factory, "cs-9")
    out = await b.build(system_prompt="规则", user_input="问")
    contents = [m.content for m in out]
    assert _u(1) not in contents
    assert _u(2) in contents
    assert _a(4) in contents
    assert sum(_message_tokens(m) for m in out[1:-1]) <= 100


async def test_at_most_one_summarize_per_build(db_session_factory) -> None:
    """D9：极端超载（8 轮 240 token）单次 build 只摘 1 次——摘要后仍超走丢轮，绝不递归再摘。"""
    await _seed_session(db_session_factory, "cs-10")
    await _seed_turns(db_session_factory, "cs-10", 8)
    hook = _Hook()
    b, _ = await _make(db_session_factory, "cs-10", summarize=hook)
    out = await b.build(system_prompt="规则", user_input="问")
    assert len(hook.calls) == 1
    payloads = await _summary_events(db_session_factory, "cs-10")
    assert [p["turn_to"] for p in payloads] == [4]  # k=ceil(8/2)
    contents = [m.content for m in out]
    assert _u(5) not in contents  # 未覆盖但装不下的最老轮被确定性丢弃
    assert _u(7) in contents
    assert _u(8) in contents
    assert sum(_message_tokens(m) for m in out[1:-1]) <= 100


async def test_oversized_summary_clipped(db_session_factory) -> None:
    """I5/I7：钩子返超长摘要 ⇒ 事件存全文（原文入流），prompt 侧 _clip 截断、历史层 ≤ 预算。

    口径经复盘补丁三两轮议定（2026-07-19）：落库 clip 与生成侧 max_tokens 双双否决——
    事件是事实源、模型原话入流（X4），租户策略不得污染不可变事实，解码级硬截断会把
    半句残话写进事实源；prompt 版面由插入期份额 clip 保护（_SUMMARY_PROMPT_SHARE，
    见 cs-14/cs-15）。
    """
    await _seed_session(db_session_factory, "cs-11")
    await _seed_turns(db_session_factory, "cs-11", 4)
    b, _ = await _make(db_session_factory, "cs-11", summarize=_Hook("超" * 500))
    out = await b.build(system_prompt="规则", user_input="问")
    payloads = await _summary_events(db_session_factory, "cs-11")
    assert payloads[0]["summary"] == "超" * 500  # 事件层全文——截断只服务 prompt
    summary_msg = next(m for m in out if _CLIP_SUFFIX in m.content)
    assert summary_msg.content.startswith(_SUMMARY_HEADER.format(turn_from=1, turn_to=2))
    assert sum(_message_tokens(m) for m in out[1:-1]) <= 100


async def test_user_input_reserved_never_evicted(db_session_factory) -> None:
    """D11：user_input 超长（200>101）⇒ 历史全丢、user 原文照放——挤掉/截断用户的话=答非所问/篡改输入。"""
    await _seed_turns(db_session_factory, "cs-12", 2)
    b, _ = await _make(db_session_factory, "cs-12")
    big = "问" * 200
    out = await b.build(system_prompt="规则", user_input=big)
    assert [m.role for m in out] == ["system", "user"]
    assert out[1].content == big


async def test_events_raw_untouched_by_summary(db_session_factory) -> None:
    """摘要只服务 prompt：压缩后 events 表旧轮原文一条不少——events 永远是事实源（00 §6.1）。"""
    await _seed_session(db_session_factory, "cs-13")
    await _seed_turns(db_session_factory, "cs-13", 4)
    b, _ = await _make(db_session_factory, "cs-13", summarize=_Hook())
    await b.build(system_prompt="规则", user_input="问")
    async with db_session_factory() as s:
        rows = (
            await s.execute(
                select(EventRecord.type, EventRecord.payload)
                .where(EventRecord.session_id == "cs-13")
                .order_by(EventRecord.seq)
            )
        ).all()
    user_payloads = [p["content"] for t, p in rows if t == "user_message"]
    assert user_payloads == [_u(1), _u(2), _u(3), _u(4)]  # 被压缩的 1、2 轮原文仍在
    assert [t for t, _ in rows].count("assistant_message") == 4
    assert [t for t, _ in rows].count("summary_updated") == 1


async def test_summary_prompt_share_caps_when_turns_queue(db_session_factory) -> None:
    """复盘补丁三：有近轮排队时摘要至多占版面份额——肥摘要不再独占历史层（最新轮盲窗关闭）。

    预算账（budget_h=100）：header 9 → allowed=91 → 份额 45；肥摘要 clip 至 45（含尾注）
    → 摘要条 54，余 46 → 恰容最新一轮 t4（30），t3 仍让位——最新轮的席位是结构保证。
    """
    await _seed_session(db_session_factory, "cs-14")
    await _seed_turns(db_session_factory, "cs-14", 4)
    b, _ = await _make(db_session_factory, "cs-14", summarize=_Hook("超" * 500))
    out = await b.build(system_prompt="规则", user_input="问")
    contents = [m.content for m in out]
    assert _u(4) in contents  # 最新轮进场——修复的靶心
    assert _a(4) in contents
    assert _u(3) not in contents  # 次新轮仍装不下：份额是保底席位不是无限席位
    summary_msg = next(m for m in out if _CLIP_SUFFIX in m.content)
    assert summary_msg.content.startswith(_SUMMARY_HEADER.format(turn_from=1, turn_to=2))
    assert sum(_message_tokens(m) for m in out[1:-1]) <= 100


async def test_summary_share_not_applied_without_queue(db_session_factory) -> None:
    """份额只在"有近轮排队"时生效：全部轮次已被覆盖 ⇒ 摘要可占满 allowed，版面不白扣。"""
    await _seed_session(db_session_factory, "cs-15")
    await _seed_turns(db_session_factory, "cs-15", 2)
    w = await EventWriter.open(db_session_factory, "cs-15", "r-old-sum")
    await w.append(EventType.SUMMARY_UPDATED, {"summary": "长" * 70, "turn_from": 1, "turn_to": 2})
    b, _ = await _make(db_session_factory, "cs-15")
    out = await b.build(system_prompt="规则", user_input="问")
    summary_msg = next(m for m in out if m.content.startswith(_SUMMARY_HEADER.format(turn_from=1, turn_to=2)))
    assert "长" * 70 in summary_msg.content  # est 70 > 份额 45 但 ≤ allowed 91：未被份额刀裁
    assert _CLIP_SUFFIX not in summary_msg.content

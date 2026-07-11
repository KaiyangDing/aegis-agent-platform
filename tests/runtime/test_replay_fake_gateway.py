"""M2.6 交付②：FakeGateway 四道回放器与 scoped 作用域视图（plans/m2.6 §4.2、§5）。

纯内存：零真实调用、零容器依赖。匹配键 = (session_id, scope, 道内序号)——
prompt 漂移不失配（03 §7）、四道游标互不影响（C10）、失配响亮抛 CassetteMismatch。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from aegis.gateway.schema import LLMChunk, LLMRequest, Message, StopChunk, TextDelta, UsageChunk
from aegis.runtime.replay import (
    Cassette,
    CassetteEntry,
    CassetteMismatch,
    FakeGateway,
    scoped_view,
)
from aegis.runtime.runtime import GatewayLike


def _entry(text: str) -> CassetteEntry:
    """text_delta + usage + stop 三件套条目。"""
    return CassetteEntry(
        chunks=(
            TextDelta(text=text),
            UsageChunk(model="qwen-plus", prompt_tokens=5, completion_tokens=3),
            StopChunk(reason="end_turn"),
        )
    )


def _cassette(**scopes: tuple[CassetteEntry, ...]) -> Cassette:
    return Cassette(session_id="cs-demo-1", scopes=dict(scopes))


def _req(session_id: str | None = "cs-demo-1") -> LLMRequest:
    return LLMRequest(
        tier="standard",
        messages=[Message(role="user", content="订单到哪了")],
        tenant_id="t-demo",
        session_id=session_id,
    )


def _first_text(chunks: list[LLMChunk]) -> str:
    first = chunks[0]
    assert isinstance(first, TextDelta)
    return first.text


class _PlainGateway:
    """没有 scoped 方法的"真网关"替身：scoped_view 对它必须直通（D10）。"""

    def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        raise NotImplementedError("本测试永不调用")


async def test_replays_chunks_in_order_main_scope() -> None:
    """回放本体：async for 收集到的序列与录入 chunk 逐一相等（类型与内容）。"""
    e = _entry("您的订单已发货。")
    fake = FakeGateway(_cassette(main=(e,)))
    got = [c async for c in fake.complete(_req())]
    assert got == list(e.chunks)


async def test_complete_equals_scoped_main() -> None:
    """裸 complete ≡ scoped("main")：两个入口一个账本，游标共同推进。"""
    fake = FakeGateway(_cassette(main=(_entry("第一"), _entry("第二"))))
    first = [c async for c in fake.complete(_req())]
    second = [c async for c in fake.scoped("main").complete(_req())]
    assert _first_text(first) == "第一"
    assert _first_text(second) == "第二"
    assert fake.remaining()["main"] == 0


async def test_scopes_have_independent_cursors() -> None:
    """C10 灵魂断言：交错调用 main→summary→main，各道各数各的，互不挪账。"""
    fake = FakeGateway(_cassette(main=(_entry("主1"), _entry("主2")), summary=(_entry("摘1"),)))
    a = [c async for c in fake.complete(_req())]
    s = [c async for c in fake.scoped("summary").complete(_req())]
    b = [c async for c in fake.complete(_req())]
    assert _first_text(a) == "主1"
    assert _first_text(s) == "摘1"
    assert _first_text(b) == "主2"


async def test_exhausted_scope_raises_cassette_mismatch() -> None:
    """道耗尽 ⇒ CassetteMismatch，诊断含 scope、已录条数、第几次调用（多出来的调用=行为漂移）。"""
    fake = FakeGateway(_cassette(main=(_entry("唯一"),)))
    _ = [c async for c in fake.complete(_req())]
    with pytest.raises(CassetteMismatch) as ei:
        _ = [c async for c in fake.complete(_req())]
    msg = str(ei.value)
    assert "main" in msg
    assert "1" in msg
    assert "2" in msg


async def test_prompt_drift_does_not_miss() -> None:
    """匹配键不是 prompt 哈希（03 §7 反向钉死）：档位/内容/租户全变，照常回放。"""
    e = _entry("回放成功")
    fake = FakeGateway(_cassette(main=(e,)))
    drifted = LLMRequest(
        tier="strong",
        messages=[Message(role="user", content="完全不同的问题")],
        tenant_id="t-x",
        session_id="cs-demo-1",
    )
    got = [c async for c in fake.complete(drifted)]
    assert got == list(e.chunks)


async def test_wrong_session_id_raises_mismatch() -> None:
    """会话对不上 ⇒ CassetteMismatch，诊断含期望/实际两个 id。"""
    fake = FakeGateway(_cassette(main=(_entry("x"),)))
    with pytest.raises(CassetteMismatch) as ei:
        _ = [c async for c in fake.complete(_req(session_id="cs-other"))]
    assert "cs-demo-1" in str(ei.value)
    assert "cs-other" in str(ei.value)


async def test_missing_session_id_raises_mismatch() -> None:
    """session_id=None 也失配——"L2 请求必带 session_id"的对齐要求由此机器强制（m2.6 §2.2）。"""
    fake = FakeGateway(_cassette(main=(_entry("x"),)))
    with pytest.raises(CassetteMismatch):
        _ = [c async for c in fake.complete(_req(session_id=None))]


def test_unknown_scope_view_rejected() -> None:
    """道名拼错取视图当场炸 ValueError——不留到回放期（构造期防呆惯例）。"""
    fake = FakeGateway(_cassette(main=(_entry("x"),)))
    with pytest.raises(ValueError, match="summry"):
        fake.scoped("summry")


async def test_cursor_advances_even_if_consumer_aborts_early() -> None:
    """D6：取首块后 break（触发 aclose），同道下一次拿到第 2 条——半途挂断也算一次调用。"""
    fake = FakeGateway(_cassette(main=(_entry("第一"), _entry("第二"))))
    stream = fake.complete(_req())
    async for _chunk in stream:
        break
    await stream.aclose()
    nxt = [c async for c in fake.complete(_req())]
    assert _first_text(nxt) == "第二"


async def test_remaining_and_assert_exhausted() -> None:
    """remaining 各道余量正确；未放完 assert_exhausted 点名道，放完通过（D14/M2.12 消费）。"""
    fake = FakeGateway(_cassette(main=(_entry("a"), _entry("b")), guard=(_entry("g"),)))
    _ = [c async for c in fake.complete(_req())]
    assert fake.remaining() == {"main": 1, "summary": 0, "guard": 1, "tool_digest": 0}
    with pytest.raises(AssertionError) as ei:
        fake.assert_exhausted()
    assert "main" in str(ei.value)
    assert "guard" in str(ei.value)
    _ = [c async for c in fake.complete(_req())]
    _ = [c async for c in fake.scoped("guard").complete(_req())]
    fake.assert_exhausted()


def test_fake_gateway_structurally_satisfies_protocol() -> None:
    """mypy 静态锁：FakeGateway 与 scoped 视图长着 GatewayLike 形状；scoped_view 直通语义（D10）。"""

    def _accepts(g: GatewayLike) -> GatewayLike:
        return g

    fake = FakeGateway(_cassette(main=(_entry("x"),)))
    _accepts(fake)
    _accepts(fake.scoped("summary"))
    plain = _PlainGateway()
    assert scoped_view(plain, "main") is plain  # 无 scoped 方法 ⇒ 直通返回自身
    assert scoped_view(fake, "guard") is not fake  # 有 scoped ⇒ 出借道视图

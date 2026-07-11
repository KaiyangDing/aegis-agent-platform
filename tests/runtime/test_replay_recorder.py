"""M2.6 交付③：Recorder 透传录制（plans/m2.6 §4.3、§5）。

半截流不入带（D5）、异常不吞不译、aclose 归还内层连接——把事故录成基线
是回放体系的头号腐蚀源。纯内存 + tmp_path，零真实调用、零容器依赖。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from pathlib import Path

import pytest

from aegis.gateway.schema import LLMChunk, LLMRequest, Message, StopChunk, TextDelta, UsageChunk
from aegis.runtime.replay import Cassette, FakeGateway, Recorder
from aegis.runtime.runtime import GatewayLike


class _Boom(RuntimeError):
    """内层流中途炸的哨兵异常：Recorder 必须原样透传（类型不变）。"""


def _chunks(text: str) -> tuple[LLMChunk, ...]:
    return (
        TextDelta(text=text),
        UsageChunk(model="qwen-plus", prompt_tokens=5, completion_tokens=3),
        StopChunk(reason="end_turn"),
    )


class _ScriptedGateway:
    """预置脚本的内层网关：每次 complete 按序消费一份脚本；可在第 N 块前抛异常；finally 计数关闭。"""

    def __init__(self, *scripts: Sequence[LLMChunk], raise_after: int | None = None) -> None:
        self._scripts = [tuple(s) for s in scripts]
        self._raise_after = raise_after
        self.closed = 0  # 内层流 finally 执行次数（aclose 或自然耗尽都 +1）

    async def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        script = self._scripts.pop(0)
        try:
            for i, chunk in enumerate(script):
                if self._raise_after is not None and i == self._raise_after:
                    raise _Boom(f"上游在第 {i} 块前断线")
                yield chunk
        finally:
            self.closed += 1


def _req(session_id: str | None = "cs-rec-1") -> LLMRequest:
    return LLMRequest(
        tier="standard",
        messages=[Message(role="user", content="订单到哪了")],
        tenant_id="t-demo",
        session_id=session_id,
    )


async def test_passthrough_preserves_chunks() -> None:
    """透传零改写：消费方拿到的序列与内层产出逐一相等。"""
    script = _chunks("您的订单已发货。")
    rec = Recorder(_ScriptedGateway(script), "cs-rec-1")
    got = [c async for c in rec.complete(_req())]
    assert got == list(script)


async def test_records_one_entry_per_call_per_scope() -> None:
    """每次调用一条 entry、按道分账（C10 的录制侧）。"""
    rec = Recorder(_ScriptedGateway(_chunks("主1"), _chunks("主2"), _chunks("守1")), "cs-rec-1")
    _ = [c async for c in rec.complete(_req())]
    _ = [c async for c in rec.complete(_req())]
    _ = [c async for c in rec.scoped("guard").complete(_req())]
    c = rec.cassette()
    assert len(c.scopes["main"]) == 2
    assert len(c.scopes["guard"]) == 1
    assert c.scopes["main"][1].chunks == _chunks("主2")
    assert c.scopes["guard"][0].chunks == _chunks("守1")


async def test_recorded_digest_is_summary_only() -> None:
    """D2 红线的机器守卫：digest 恰四键，prompt 原文（用户对话）绝不落盘。"""
    rec = Recorder(_ScriptedGateway(_chunks("x")), "cs-rec-1")
    _ = [c async for c in rec.complete(_req())]
    digest = rec.cassette().scopes["main"][0].request_digest
    assert set(digest) == {"tier", "message_count", "tool_names", "prompt_sha256"}
    assert "订单到哪了" not in str(digest)


async def test_midstream_exception_not_recorded_and_propagates() -> None:
    """内层第 2 块后抛 ⇒ 异常原样穿出（不吞不译），该道零新增条目（D5 半截流不入带）。"""
    rec = Recorder(_ScriptedGateway(_chunks("x"), raise_after=2), "cs-rec-1")
    got: list[LLMChunk] = []
    with pytest.raises(_Boom):
        async for chunk in rec.complete(_req()):
            got.append(chunk)
    assert len(got) == 2  # 前两块已透传给消费方
    assert rec.cassette().scopes == {}


async def test_early_close_not_recorded_and_inner_closed() -> None:
    """消费方取 1 块后 aclose ⇒ 不入带 + 内层连接被归还（inner 的 finally 必须执行）。"""
    inner = _ScriptedGateway(_chunks("x"))
    rec = Recorder(inner, "cs-rec-1")
    stream = rec.complete(_req())
    _ = await anext(stream)
    await stream.aclose()
    assert inner.closed == 1
    assert rec.cassette().scopes == {}


async def test_session_id_mismatch_rejected() -> None:
    """Recorder 绑定单会话：请求带别的 session_id ⇒ ValueError（录制脚本 bug 快速失败）。"""
    rec = Recorder(_ScriptedGateway(_chunks("x")), "cs-rec-1")
    with pytest.raises(ValueError, match="cs-other"):
        _ = [c async for c in rec.complete(_req(session_id="cs-other"))]


async def test_record_save_load_replay_roundtrip(tmp_path: Path) -> None:
    """缝的端到端：录 → save → load → FakeGateway 回放，chunk 序列与原始一致。"""
    main_script, summary_script = _chunks("您的订单已发货。"), _chunks("会话摘要文本")
    rec = Recorder(_ScriptedGateway(main_script, summary_script), "cs-rec-1")
    _ = [c async for c in rec.complete(_req())]
    _ = [c async for c in rec.scoped("summary").complete(_req())]
    p = tmp_path / "recorded.json"
    rec.save(p)
    fake = FakeGateway(Cassette.load(p))
    replay_main = [c async for c in fake.complete(_req())]
    replay_summary = [c async for c in fake.scoped("summary").complete(_req())]
    assert replay_main == list(main_script)
    assert replay_summary == list(summary_script)
    fake.assert_exhausted()


def test_recorder_structurally_satisfies_protocol() -> None:
    """mypy 静态锁：Recorder 与其 scoped 视图长着 GatewayLike 形状。"""

    def _accepts(g: GatewayLike) -> GatewayLike:
        return g

    rec = Recorder(_ScriptedGateway(_chunks("x")), "cs-rec-1")
    _accepts(rec)
    _accepts(rec.scoped("tool_digest"))

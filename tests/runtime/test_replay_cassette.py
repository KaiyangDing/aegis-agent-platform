"""M2.6 交付①：cassette 格式与原子载入保存（plans/m2.6 §4.1、§5）。

纯内存 + tmp_path：零真实调用、零容器依赖——未启 Docker 的机器上也必须全绿。
资产路径用 __file__ 锚定（记忆教训：脚本落盘锚定项目根，禁止相对 cwd）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from aegis.gateway.schema import (
    LLMRequest,
    Message,
    StopChunk,
    TextDelta,
    ToolCall,
    ToolCallChunk,
    ToolSpec,
    UsageChunk,
)
from aegis.runtime.replay import FORMAT_VERSION, Cassette, CassetteEntry, request_digest

CASSETTES = Path(__file__).resolve().parents[1] / "cassettes"


def _chunk_dicts(text: str = "已发货。") -> list[dict[str, Any]]:
    """text_delta + usage + stop 三件套（JSON 形态，手搓 cassette 文件用）。"""
    return [
        {"type": "text_delta", "text": text},
        {"type": "usage", "model": "qwen-plus", "prompt_tokens": 10, "completion_tokens": 5, "cached": False},
        {"type": "stop", "reason": "end_turn"},
    ]


def _doc(**overrides: Any) -> dict[str, Any]:
    """合法 cassette 文档基座，按需覆盖字段制造坏样本。"""
    base: dict[str, Any] = {
        "format_version": 1,
        "session_id": "cs-demo-1",
        "scopes": {"main": [{"request_digest": {}, "chunks": _chunk_dicts()}]},
    }
    base.update(overrides)
    return base


def _write(tmp_path: Path, data: dict[str, Any]) -> Path:
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def _mini() -> Cassette:
    return Cassette(
        session_id="cs-demo-1",
        scopes={"main": (CassetteEntry(chunks=(TextDelta(text="您的订单已发货。"), StopChunk(reason="end_turn"))),)},
    )


def _req(**kw: Any) -> LLMRequest:
    defaults: dict[str, Any] = {
        "tier": "standard",
        "messages": [Message(role="user", content="订单到哪了")],
        "tenant_id": "t-demo",
        "session_id": "cs-demo-1",
    }
    defaults.update(kw)
    return LLMRequest(**defaults)


def test_minimal_demo_asset_loads() -> None:
    """资产自检：手写 minimal_demo 可载入；chunk 经判别联合还原为真类型（schema.py:6 往返红利）。"""
    c = Cassette.load(CASSETTES / "minimal_demo.json")
    assert c.session_id == "cs-demo-1"
    assert len(c.scopes["main"]) == 2
    assert len(c.scopes["summary"]) == 1
    assert isinstance(c.scopes["main"][0].chunks[0], TextDelta)
    assert isinstance(c.scopes["main"][1].chunks[0], ToolCallChunk)


def test_format_version_mismatch_rejected(tmp_path: Path) -> None:
    """版本不认 ⇒ ValueError，消息含两个版本号（载入期防呆，D7）。"""
    p = _write(tmp_path, _doc(format_version=2))
    with pytest.raises(ValueError) as ei:
        Cassette.load(p)
    assert "2" in str(ei.value)
    assert str(FORMAT_VERSION) in str(ei.value)


def test_unknown_scope_key_rejected(tmp_path: Path) -> None:
    """道名拼错（summry）⇒ 载入期爆炸并点名坏键——不留到回放期静默错配（C10）。"""
    p = _write(tmp_path, _doc(scopes={"summry": [{"chunks": _chunk_dicts()}]}))
    with pytest.raises(ValueError, match="summry"):
        Cassette.load(p)


def test_entry_without_stop_tail_rejected(tmp_path: Path) -> None:
    """不以 StopChunk 收尾 ⇒ ValueError——半截流不许当基线（与缓存完整性守卫同源）。"""
    p = _write(tmp_path, _doc(scopes={"main": [{"chunks": [{"type": "text_delta", "text": "半截"}]}]}))
    with pytest.raises(ValueError, match="StopChunk"):
        Cassette.load(p)


def test_empty_chunks_rejected(tmp_path: Path) -> None:
    """chunks 为空 ⇒ ValueError（空流回放没有意义，录进来必是 bug）。"""
    p = _write(tmp_path, _doc(scopes={"main": [{"chunks": []}]}))
    with pytest.raises(ValueError, match="StopChunk"):
        Cassette.load(p)


def test_bad_chunk_type_raises_validation_error(tmp_path: Path) -> None:
    """chunk type 拼错 ⇒ pydantic ValidationError 裸抛——bug 信号不包装（判别联合守卫）。"""
    p = _write(tmp_path, _doc(scopes={"main": [{"chunks": [{"type": "text_deltaa", "text": "x"}]}]}))
    with pytest.raises(ValidationError):
        Cassette.load(p)


def test_save_load_roundtrip_preserves_chunks(tmp_path: Path) -> None:
    """四类 chunk save→load 逐字段还原（M1.1 无损 JSON 往返设计红利）。"""
    call = ToolCall(id="call-1", name="demo_order_query", arguments_json='{"order_id": "A-1"}')
    entry = CassetteEntry(
        chunks=(
            TextDelta(text="您好，"),
            ToolCallChunk(tool_call=call),
            UsageChunk(model="qwen-plus", prompt_tokens=3, completion_tokens=2, cached=True),
            StopChunk(reason="tool_calls"),
        ),
        request_digest={"tier": "standard"},
    )
    guard_entry = CassetteEntry(chunks=(TextDelta(text="低"), StopChunk(reason="end_turn")))
    c1 = Cassette(session_id="cs-rt-1", scopes={"main": (entry,), "guard": (guard_entry,)})
    p = tmp_path / "rt.json"
    c1.save(p)
    c2 = Cassette.load(p)
    assert c2.session_id == c1.session_id
    assert c2.scopes == c1.scopes


def test_save_is_atomic_replace_and_no_tmp_left(tmp_path: Path) -> None:
    """save 覆盖既有文件（os.replace——Windows rename 不覆盖）且不留 *.tmp 残留（D11）。"""
    p = tmp_path / "c.json"
    p.write_text("旧内容", encoding="utf-8")
    _mini().save(p)
    assert json.loads(p.read_text(encoding="utf-8"))["session_id"] == "cs-demo-1"
    assert list(tmp_path.glob("*.tmp")) == []


def test_save_writes_utf8_lf_no_ascii_escape(tmp_path: Path) -> None:
    """落盘字节：UTF-8 中文原文（无 \\uXXXX 转义）、LF 行尾——cassette 进 git，diff 必须可读。"""
    p = tmp_path / "c.json"
    _mini().save(p)
    raw = p.read_bytes()
    assert "您的订单已发货。".encode() in raw
    assert b"\\u" not in raw
    assert b"\r\n" not in raw


def test_request_digest_ignores_volatile_ids() -> None:
    """D2 摘要域恰四键；易变字段不进指纹（复用缓存语义本体口径）；content 变则指纹变。"""
    a = request_digest(_req(session_id="cs-1", tenant_id="t-a", deadline_s=5.0))
    b = request_digest(_req(session_id="cs-2", tenant_id="t-b"))
    assert a["prompt_sha256"] == b["prompt_sha256"]  # request_id 亦每次不同（默认工厂），一并覆盖
    c = request_digest(_req(messages=[Message(role="user", content="改了一个字")]))
    assert c["prompt_sha256"] != a["prompt_sha256"]
    assert set(a) == {"tier", "message_count", "tool_names", "prompt_sha256"}
    d = request_digest(_req(tools=[ToolSpec(name="demo_order_query", description="查订单", parameters={})]))
    assert d["tool_names"] == ["demo_order_query"]

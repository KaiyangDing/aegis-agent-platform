"""M3.10 交付②：SSE 线格式编码器（sse.encode_frame）——帧协议的字节面契约。

线格式是前端 EventSource 与 curl -N 的消费契约：event:/data:/id: 三行、
data 单行 JSON（换行经 json 转义，绝不出现裸换行撕帧）、空行收帧。
"""

from __future__ import annotations

import pytest

from aegis.api.sse import encode_frame
from aegis.apps.support.service import ChatFrame


def test_token_frame_wire_format() -> None:
    assert encode_frame(ChatFrame("token", {"text": "你好"})) == 'event: token\ndata: {"text": "你好"}\n\n'


def test_id_line_present_only_with_seq() -> None:
    """id: 仅 GET 通道回放事件时在场（=events.seq，Last-Event-ID 续传的物质基础）。"""
    assert encode_frame(ChatFrame("token", {"text": "x"}, seq=7)).startswith("id: 7\nevent: token\n")
    assert "id:" not in encode_frame(ChatFrame("token", {"text": "x"}))


def test_data_single_line_newlines_escaped() -> None:
    """data 必须单行：文本内换行经 JSON 转义——裸换行会让 SSE 解析器把半帧当整帧。"""
    wire = encode_frame(ChatFrame("token", {"text": "第一行\n第二行"}))
    assert wire.endswith("\n\n")
    assert "\n" not in wire[:-2].split("data: ", 1)[1]
    assert "\\n" in wire


def test_cjk_not_ascii_escaped() -> None:
    """ensure_ascii=False：中文原样出线（调试可读、字节数减半）。"""
    assert "你好" in encode_frame(ChatFrame("token", {"text": "你好"}))


@pytest.mark.parametrize(
    "kind",
    ["token", "user_message", "tool_status", "approval_pending", "done", "error", "message_reset", "handoff"],
)
def test_all_frame_kinds_encode(kind: str) -> None:
    """帧词汇全表可编码（ADR-007 五帧 + D11 message_reset + handoff + (73) user_message）。"""
    assert encode_frame(ChatFrame(kind, {})).startswith(f"event: {kind}\n")

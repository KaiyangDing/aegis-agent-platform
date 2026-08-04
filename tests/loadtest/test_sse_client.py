"""M5.1 交付③：SSE 帧解析纯函数九测（零 IO 零时序零 aegis 依赖——它进 CI 的资格所在）。"""

from __future__ import annotations

from scripts.loadtest.sse_client import SSEFrame, iter_sse_frames


def _frames(*chunks: bytes) -> list[SSEFrame]:
    return list(iter_sse_frames(chunks))


def test_single_frame_event_and_data() -> None:
    got = _frames(b'event: token\ndata: {"text": "x"}\n\n')
    assert got == [SSEFrame(event="token", data='{"text": "x"}')]


def test_multiline_data_joined() -> None:
    got = _frames(b"event: token\ndata: a\ndata: b\n\n")
    assert got[0].data == "a\nb"  # SSE 规范：多 data 行以 \n 连接


def test_frame_split_across_chunks() -> None:
    """核心场景：iter_content 任意切割——帧从中间断开，缓冲拼接后仍完整解析。"""
    got = _frames(b"event: to", b"ken\ndata: hel", b"lo\n\n")
    assert got == [SSEFrame(event="token", data="hello")]


def test_trailing_partial_frame_not_emitted() -> None:
    got = _frames(b"event: token\ndata: a\n\nevent: done\ndata: b")  # 尾部无 \n\n
    assert [f.event for f in got] == ["token"]


def test_crlf_tolerated() -> None:
    got = _frames(b"event: done\r\ndata: {}\r\n\r\n")
    assert got == [SSEFrame(event="done", data="{}")]


def test_comment_line_ignored() -> None:
    got = _frames(b": keep-alive\n\nevent: token\ndata: x\n\n")
    assert got == [SSEFrame(event="token", data="x")]  # 纯注释帧不产出


def test_id_field_captured() -> None:
    got = _frames(b"id: 42\nevent: token\ndata: x\n\n")
    assert got[0].id == "42"  # GET 通道 Last-Event-ID 续传依赖


def test_colon_space_optional() -> None:
    assert _frames(b"data:x\n\n") == _frames(b"data: x\n\n")


def test_multiple_frames_in_one_chunk() -> None:
    got = _frames(b"event: token\ndata: a\n\nevent: done\ndata: b\n\n")
    assert [f.event for f in got] == ["token", "done"]

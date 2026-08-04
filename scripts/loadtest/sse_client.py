"""SSE 帧解析纯函数（M5.1 交付①；scripts 侧唯一进 CI 的逻辑——D4）。

bytes 进、SSEFrame 出：不做 IO、不吞异常、不 import aegis 也不 import locust
（gevent×asyncio 隔离纪律 D3 的两头都靠它解耦）。帧词汇实况 **8 种**（M5.0 走查⑵：
token/user_message/tool_status/approval_pending/handoff/done/error/message_reset）——
本解析器只按 SSE 规范切帧取字段，**不校验帧名**（词汇归调用方，协议归这里）。
不做 JSON 解析：data 载荷的解释归调用方。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

_FRAME_SEPARATORS = (b"\r\n\r\n", b"\n\n")


@dataclass(frozen=True, slots=True)
class SSEFrame:
    event: str  # 帧名（8 种词汇见模块 docstring；解析器不校验）
    data: str  # 多个 data: 行按 SSE 规范以 "\n" 连接
    id: str | None = None  # 对应事件流 seq——GET 通道 Last-Event-ID 续传用


def _split_one_frame(buffer: bytes) -> tuple[bytes, bytes] | None:
    """从缓冲头部切出一帧原文；无完整帧返回 None（尾部半帧留在缓冲——核心不变量）。"""
    best: tuple[int, int] | None = None  # (分隔符起点, 分隔符长度)
    for sep in _FRAME_SEPARATORS:
        idx = buffer.find(sep)
        if idx != -1 and (best is None or idx < best[0]):
            best = (idx, len(sep))
    if best is None:
        return None
    idx, sep_len = best
    return buffer[:idx], buffer[idx + sep_len :]


def _parse_frame(raw: bytes) -> SSEFrame | None:
    """帧内逐行取 event/data/id 三字段（冒号后一个可选空格）；注释行与空字段名行忽略；
    帧内无任何字段 → None（丢弃）。"""
    event = ""
    data_lines: list[str] = []
    frame_id: str | None = None
    seen_field = False
    for raw_line in raw.replace(b"\r\n", b"\n").split(b"\n"):
        line = raw_line.decode("utf-8", errors="replace")
        if not line or line.startswith(":"):  # 空行/注释行（": keep-alive"）
            continue
        name, _, value = line.partition(":")
        if not name:
            continue
        if value.startswith(" "):  # 冒号后一个可选空格（SSE 规范）
            value = value[1:]
        if name == "event":
            event, seen_field = value, True
        elif name == "data":
            data_lines.append(value)
            seen_field = True
        elif name == "id":
            frame_id, seen_field = value, True
    if not seen_field:
        return None
    return SSEFrame(event=event, data="\n".join(data_lines), id=frame_id)


def iter_sse_frames(chunks: Iterable[bytes]) -> Iterator[SSEFrame]:
    """把任意切割的 bytes 流重组为 SSE 帧序列（iter_content 的 chunk 边界不落在
    帧边界上是常态——T3 的解法就是自己持缓冲切帧）。"""
    buffer = b""
    for chunk in chunks:
        buffer += chunk
        while (split := _split_one_frame(buffer)) is not None:
            raw, buffer = split
            frame = _parse_frame(raw)
            if frame is not None:
                yield frame

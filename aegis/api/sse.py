"""SSE 线格式编码（M3.10②；ADR-007/D11/14j 拍板Ⅲ）。

帧类型是 service.ChatFrame（单一帧类型贯穿服务层→通道，不设翻译层）；本模块
只管字节面：event:/data:/id: 三行 + 空行收帧。data 单行 JSON（换行经 json 转义
——裸换行会被 SSE 解析器当帧界撕开）；ensure_ascii=False 中文原样出线。
"""

from __future__ import annotations

import json

from aegis.apps.support.service import ChatFrame


def encode_frame(frame: ChatFrame) -> str:
    """ChatFrame → SSE 帧字节面。id: 仅 seq 在场时写（GET 通道回放事件=events.seq——
    EventSource 断线自动带 Last-Event-ID 续传的物质基础，每帧都写才续得准）。"""
    lines: list[str] = []
    if frame.seq is not None:
        lines.append(f"id: {frame.seq}")
    lines.append(f"event: {frame.kind}")
    lines.append(f"data: {json.dumps(dict(frame.data), ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"

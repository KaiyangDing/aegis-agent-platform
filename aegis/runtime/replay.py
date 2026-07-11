"""录制回放基建（M2.6，03 §7）：cassette 格式 + FakeGateway + Recorder + C31 归一化。

"测试与 CI 全程零真实调用"（00 §6.0）的地基：M2.7+ 循环测试、M2.12"中断-恢复
逐事件一致"强断言、M4.3 零 token CI 回归都踩在这里。
匹配键 = (session_id, scope, 道内序号)——明确排除 prompt 哈希（03 §7：prompt
微调不至于全量 miss）；"轮次"按调用源分四道独立计数（C10），任一失配响亮抛
CassetteMismatch，绝不静默错配。
敏感字段纪律（D2/D3）：request 侧只落摘要域（prompt 原文不落盘）；chunk 是
回放本体、原样全量——录制只用虚构演示数据（tests/cassettes/README.md）。
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from aegis.gateway.schema import LLMChunk, LLMRequest, StopChunk, chunk_list_adapter

FORMAT_VERSION: int = 1
"""cassette 文件格式版本。字段语义变更时 +1 并保留旧加载路径（与事件 SCHEMA_VERSION 同哲学）。"""

Scope = Literal["main", "summary", "guard", "tool_digest"]
"""C10 四道调用源：主循环 / 滚动摘要（ContextBuilder）/ 守卫分类（M2.8）/ 结果摘要（ToolExecutor）。
用 Literal 不用 StrEnum：道名进 JSON 与函数参数，mypy 在调用点拦拼写，无枚举序列化噪音（D13）。"""

SCOPES: tuple[Scope, ...] = ("main", "summary", "guard", "tool_digest")


class CassetteMismatch(RuntimeError):
    """回放失配（C10）：会话/道/序号任一对不上，响亮抛出——绝不静默错配或返回兜底流。"""


def request_digest(req: LLMRequest) -> dict[str, Any]:
    """请求摘要域（D2 拍板：只记摘要不记 messages 原文——PII 不落盘的机械保证）。

    仅供失配诊断与重录 diff 定位，绝不参与匹配（参与即退化回 prompt 哈希，03 §7）。
    prompt_sha256 复用精确缓存的语义本体口径（cache.py:38-42）：排除四个易变字段
    后 canonical JSON 再哈希——同一语义请求跨会话/跨租户得到同一指纹。
    """
    essence = req.model_dump(exclude={"request_id", "session_id", "tenant_id", "deadline_s"})
    blob = json.dumps(essence, sort_keys=True, ensure_ascii=False)
    return {
        "tier": req.tier,
        "message_count": len(req.messages),
        "tool_names": [t.name for t in req.tools],
        "prompt_sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
    }


@dataclass(frozen=True, slots=True)
class CassetteEntry:
    """一次 LLM 调用的录制条目：chunks 是回放本体，request_digest 只是诊断域。"""

    chunks: tuple[LLMChunk, ...]
    request_digest: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Cassette:
    """一盘录制带：一个会话、四道各自的条目序列。加载后只读（frozen + tuple）。"""

    session_id: str
    scopes: Mapping[str, tuple[CassetteEntry, ...]]
    format_version: int = FORMAT_VERSION

    @classmethod
    def load(cls, path: Path) -> Cassette:
        """载入 + 构造期防呆（ValueError，仓库惯例）：拼错道名/坏版本在载入期爆炸，不留到回放期。"""
        data = json.loads(path.read_text(encoding="utf-8"))
        version = data.get("format_version")
        if version != FORMAT_VERSION:
            raise ValueError(f"{path}: format_version={version}，本代码只认 {FORMAT_VERSION}")
        session_id = data.get("session_id")
        if not session_id:
            raise ValueError(f"{path}: session_id 缺失或为空——匹配键的第一段不能没有")
        raw_scopes: dict[str, Any] = data.get("scopes", {})
        unknown = set(raw_scopes) - set(SCOPES)
        if unknown:
            raise ValueError(f"{path}: 未知道名 {sorted(unknown)}——合法四道为 {list(SCOPES)}（C10）")
        scopes: dict[str, tuple[CassetteEntry, ...]] = {}
        for scope, entries in raw_scopes.items():
            parsed: list[CassetteEntry] = []
            for i, entry in enumerate(entries):
                # 坏 chunk（type 拼错等）由 pydantic ValidationError 裸抛——bug 信号不包装
                chunks = tuple(chunk_list_adapter.validate_python(entry["chunks"]))
                if not chunks or not isinstance(chunks[-1], StopChunk):
                    raise ValueError(
                        f"{path}: {scope} 道第 {i + 1} 条不以 StopChunk 收尾——"
                        f"半截流不许当基线（与缓存完整性守卫同源，cache.py:55-60）"
                    )
                parsed.append(CassetteEntry(chunks=chunks, request_digest=entry.get("request_digest", {})))
            scopes[scope] = tuple(parsed)
        return cls(session_id=session_id, scopes=scopes)

    def dump(self) -> dict[str, Any]:
        """导出为可 JSON 化的 dict（键序固定：format_version → session_id → scopes）。"""
        return {
            "format_version": self.format_version,
            "session_id": self.session_id,
            "scopes": {
                scope: [
                    {
                        "request_digest": dict(entry.request_digest),
                        "chunks": chunk_list_adapter.dump_python(list(entry.chunks), mode="json"),
                    }
                    for entry in entries
                ]
                for scope, entries in self.scopes.items()
            },
        }

    def save(self, path: Path) -> None:
        """原子落盘（D11）：同目录 tmp + os.replace——Windows rename 不覆盖、跨卷 replace 非原子。

        UTF-8 / ensure_ascii=False / LF：cassette 要进 git，diff 必须可读（06 §4 编码坑）。
        """
        text = json.dumps(self.dump(), ensure_ascii=False, indent=2) + "\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

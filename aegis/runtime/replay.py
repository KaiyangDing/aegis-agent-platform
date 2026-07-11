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
from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from aegis.gateway.schema import LLMChunk, LLMRequest, StopChunk, chunk_list_adapter
from aegis.runtime.events import AgentEvent
from aegis.runtime.runtime import GatewayLike

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


@runtime_checkable
class SupportsScoped(Protocol):
    """能出借作用域视图的网关（FakeGateway/Recorder）；真实网关不满足 → scoped_view 直通。"""

    def scoped(self, scope: str) -> GatewayLike: ...


def scoped_view(gateway: GatewayLike, scope: str) -> GatewayLike:
    """统一取视图入口（D10）：组装方不做类型判断——能出借视图的出借，否则直通自身。

    真实网关的"作用域"没有意义（每次调用都是真钱真流量），直通即正确语义。
    """
    if isinstance(gateway, SupportsScoped):
        return gateway.scoped(scope)
    return gateway


class FakeGateway:
    """cassette 回放器：L2 眼中与真网关同形（GatewayLike），LLM 由录制带扮演。

    四道游标互不影响（C10）；裸 complete ≡ scoped("main")。每次回放一个新实例——
    游标是消费进度，跨用例共享实例=错配之源。
    start_cursors 给 M2.12 中断-恢复测试用：恢复段把某道游标推到第 k 号，
    兑现"新 run 从道内第 k 号继续匹配"；重放被作废条目 = 设回 k-1。
    """

    def __init__(self, cassette: Cassette, *, start_cursors: Mapping[str, int] | None = None) -> None:
        self._cassette = cassette
        self._cursors: dict[str, int] = {s: 0 for s in SCOPES}
        if start_cursors is not None:
            for scope, at in start_cursors.items():
                if scope not in SCOPES:
                    raise ValueError(f"start_cursors 含未知道名 {scope!r}——合法四道为 {list(SCOPES)}")
                recorded = len(cassette.scopes.get(scope, ()))
                if not 0 <= at <= recorded:
                    raise ValueError(
                        f"start_cursors[{scope!r}]={at} 越界——该道已录 {recorded} 条（合法 0..{recorded}）"
                    )
                self._cursors[scope] = at

    def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        return self._replay("main", req)

    def scoped(self, scope: str) -> GatewayLike:
        if scope not in SCOPES:
            raise ValueError(f"未知道名 {scope!r}——合法四道为 {list(SCOPES)}（C10）")
        return _FakeScopedView(self, scope)

    def remaining(self) -> dict[str, int]:
        """各道未消费条数——排障与 assert_exhausted 的数据源。"""
        return {s: len(self._cassette.scopes.get(s, ())) - self._cursors[s] for s in SCOPES}

    def assert_exhausted(self) -> None:
        """录了没放完 = 行为轨迹变短，也是漂移（D14：M2.12 强断言必调，普通单测可选）。"""
        leftovers = {s: n for s, n in self.remaining().items() if n > 0}
        if leftovers:
            raise AssertionError(f"cassette 未放完：各道剩余 {leftovers}")

    async def _replay(self, scope: str, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        """回放一条：校验会话 → 取道内当前条目 → 先推进游标（D6）→ 原样产出。"""
        if req.session_id != self._cassette.session_id:
            raise CassetteMismatch(
                f"session_id 失配：期望 {self._cassette.session_id!r}，请求带 {req.session_id!r}"
                f"（scope={scope}；L2 发出的请求必带 session_id——m2.6 §2.2 对齐要求）；"
                f"request_digest={request_digest(req)}"
            )
        entries: tuple[CassetteEntry, ...] = self._cassette.scopes.get(scope, ())
        i = self._cursors[scope]
        if i >= len(entries):
            raise CassetteMismatch(
                f"{scope} 道耗尽：已录 {len(entries)} 条，本次是该道第 {i + 1} 次调用——"
                f"多出来的调用就是行为漂移（C10）；request_digest={request_digest(req)}"
            )
        # D6：先推进游标再 yield——消费方首块后挂断也算一次调用（与真实调用语义一致），
        # 半途 break 不会导致下次重复回放同一条目（静默错配之源）
        self._cursors[scope] = i + 1
        for chunk in entries[i].chunks:
            yield chunk


class _FakeScopedView:
    """某一道的窄视图：消费方只看到 GatewayLike 形状，游标记账在宿主 FakeGateway。"""

    def __init__(self, host: FakeGateway, scope: str) -> None:
        self._host = host
        self._scope = scope

    def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        return self._host._replay(self._scope, req)


class Recorder:
    """透传录制器：包住真实网关，流原样过手、逐 chunk 记录，显式 save 落盘（M2.11 消费）。

    完整性守卫（D5，与 ExactCache 入库守卫同哲学）：只有自然走完的流才入带——
    半截流（上游异常/消费方提前挂断）绝不录成基线；异常不吞不译不重试（异常契约仍归 00 §2.2）。
    """

    def __init__(self, inner: GatewayLike, session_id: str) -> None:
        self._inner = inner
        self._session_id = session_id
        self._entries: dict[str, list[CassetteEntry]] = {s: [] for s in SCOPES}

    def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        return self._record("main", req)

    def scoped(self, scope: str) -> GatewayLike:
        if scope not in SCOPES:
            raise ValueError(f"未知道名 {scope!r}——合法四道为 {list(SCOPES)}（C10）")
        return _RecorderScopedView(self, scope)

    def cassette(self) -> Cassette:
        """当前已录内容的不可变快照（空道不写入，cassette 文件干净）；录制继续不影响已取快照。"""
        return Cassette(
            session_id=self._session_id,
            scopes={s: tuple(entries) for s, entries in self._entries.items() if entries},
        )

    def save(self, path: Path) -> None:
        self.cassette().save(path)

    async def _record(self, scope: str, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        """录一条：透传零改写；done 只在自然走完后置位——半截流不入带（D5）。"""
        if req.session_id != self._session_id:
            raise ValueError(
                f"录制会话失配：Recorder 绑定 {self._session_id!r}，请求带 {req.session_id!r}——录制脚本 bug，快速失败"
            )
        digest = request_digest(req)  # D2：只录摘要域，prompt 原文不落盘
        stream = self._inner.complete(req)
        buffer: list[LLMChunk] = []
        done = False
        try:
            async for chunk in stream:
                buffer.append(chunk)
                yield chunk  # 透传零改写：不缓不重排不复制
            done = True  # 只有 async for 自然走完才到这行——GeneratorExit 与中途异常都到不了
        finally:
            await stream.aclose()  # 消费方提前挂断/异常时归还底层连接（resilience 同款纪律）
            if done:
                self._entries[scope].append(CassetteEntry(chunks=tuple(buffer), request_digest=digest))


class _RecorderScopedView:
    """某一道的录制视图：形状即 GatewayLike，条目记账在宿主 Recorder。"""

    def __init__(self, host: Recorder, scope: str) -> None:
        self._host = host
        self._scope = scope

    def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        return self._host._record(self._scope, req)


_EXEMPT_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {"latency_ms", "duration_ms", "usage", "prompt_tokens", "completion_tokens", "expires_at"}
)
"""C31 豁免键（只滴 payload 顶层——递归滴除会误伤 result 原文里的同名业务字段，D12）：
墙钟产物（latency/duration/expires_at）与供应商实测 usage 数值，重录/真实运行必然波动。"""


def normalize_event(event: AgentEvent, *, id_aliases: Mapping[str, str] | None = None) -> dict[str, Any]:
    """C31 单事件归一化（字段表 plans/m2.6 §3.3）。

    参与比较：type / schema_version / payload 其余全部键值；豁免：顶层墙钟与 usage 键。
    tool_call_id/event_id 命中别名表 → 替换（幂等引用结构保真）；不命中 → 保留原值
    （引用流外事件=bug，让断言响亮失败）。payload 先做 canonical JSON 往返——
    "刚 yield 的事件"（含 Decimal 等原生对象）与"DB 读回的事件"（JSONB 已 JSON 化）才可比。
    """
    aliases: Mapping[str, str] = id_aliases or {}
    payload: dict[str, Any] = json.loads(json.dumps(dict(event.payload), ensure_ascii=False, default=str))
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _EXEMPT_PAYLOAD_KEYS:
            continue
        if key in ("tool_call_id", "event_id") and isinstance(value, str):
            normalized[key] = aliases.get(value, value)
        else:
            normalized[key] = value
    return {"type": event.type.value, "schema_version": event.schema_version, "payload": normalized}


def normalize_events(events: Sequence[AgentEvent]) -> list[dict[str, Any]]:
    """C31 流级归一化：`normalize_events(A) == normalize_events(B)` 即行为轨迹等价。

    纯函数（不读时钟/全局状态）。事件 id 按流序别名 e1..eN；approval_id 按首现顺序
    别名 a1..aM（别名表跨整个流共享）。session_id/run_id/seq 不进输出——相对序由
    列表顺序承载，"seq 连续合法"是独立的不变量断言，不混进等价性（§3.3）。
    """
    id_aliases = {e.id: f"e{i + 1}" for i, e in enumerate(events)}
    out = [normalize_event(e, id_aliases=id_aliases) for e in events]
    approval_aliases: dict[str, str] = {}
    for item in out:
        value = item["payload"].get("approval_id")
        if isinstance(value, str):
            item["payload"]["approval_id"] = approval_aliases.setdefault(value, f"a{len(approval_aliases) + 1}")
    return out

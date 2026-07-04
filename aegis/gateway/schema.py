"""网关统一协议：所有供应商适配器的输入输出都以这里的模型为准。

设计原则：
- 中立表示：不偏向任何供应商的线格式，OpenAI/Anthropic 由各自适配器双向映射；
- 网关是笨管道：tool 参数保持原始 JSON 字符串，解析与校验是 L2 的职责；
- 可序列化：所有模型可无损 JSON 往返——M2 的录制回放直接依赖这一点。
"""

from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, TypeAdapter

Tier = Literal["fast", "standard", "strong"]
Role = Literal["system", "user", "assistant", "tool"]


class ToolSpec(BaseModel):
    """暴露给模型的工具声明。parameters 是 JSON Schema（L2 生成，网关不解释）。"""

    name: str
    description: str
    parameters: dict


class ToolCall(BaseModel):
    """模型发起的一次工具调用。

    arguments_json 保持模型输出的原始字符串——可能不是合法 JSON。
    网关不解析：怎么处理坏参数是 L2 的业务决策，不是传输层的。
    """

    id: str
    name: str
    arguments_json: str


class Message(BaseModel):
    role: Role
    content: str = ""  # v1 只支持文本（多模态是明确的非目标）
    tool_calls: list[ToolCall] = []  # 仅 assistant 消息可能非空
    tool_call_id: str | None = None  # 仅 role="tool" 的结果消息使用


class LLMRequest(BaseModel):
    tier: Tier  # 调用方声明档位，永远不写模型名
    messages: list[Message] = Field(min_length=1)
    tools: list[ToolSpec] = []
    temperature: float | None = None  # None = 用供应商默认值
    max_tokens: int | None = None
    tenant_id: str  # 计量/缓存/限流都按租户算账，必填
    session_id: str | None = None  # 进 usage_ledger，会话维度对账用
    request_id: str = Field(default_factory=lambda: uuid4().hex)


# ---- 流式响应的四种块（运行时契约 03 §7 定死的四类）----


class TextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class ToolCallChunk(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    tool_call: ToolCall  # v1：工具调用轮整体接收，不做增量解析


class UsageChunk(BaseModel):
    type: Literal["usage"] = "usage"
    model: str  # 实际执行的模型（路由/降级后可能变）
    prompt_tokens: int
    completion_tokens: int


class StopChunk(BaseModel):
    type: Literal["stop"] = "stop"
    reason: Literal["end_turn", "tool_calls", "max_tokens"]


LLMChunk = Annotated[
    TextDelta | ToolCallChunk | UsageChunk | StopChunk,
    Field(discriminator="type"),  # 按 type 字段自动还原成正确的子类型
]

chunk_adapter: TypeAdapter[LLMChunk] = TypeAdapter(LLMChunk)

"""真实验证工具调用：给模型一个天气工具，问天气，期待它返回 tool_call 而不是瞎编。

uv run python scripts/smoke_tool_call.py   （qwen-plus 一次约 0.01 元）
"""

import asyncio

from aegis.core.config import get_settings
from aegis.gateway.providers.openai_compat import OpenAICompatProvider
from aegis.gateway.schema import LLMRequest, Message, ToolSpec


async def main() -> None:
    s = get_settings()
    provider = OpenAICompatProvider(
        name="bailian",
        base_url=s.dashscope_base_url,
        api_key=s.dashscope_api_key.get_secret_value(),
    )
    weather = ToolSpec(
        name="get_weather",
        description="查询指定城市的当前天气。",
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市名，如：杭州"}},
            "required": ["city"],
        },
    )
    req = LLMRequest(
        tier="standard",
        tenant_id="smoke",
        messages=[Message(role="user", content="杭州现在天气怎么样？")],
        tools=[weather],
    )
    async for chunk in provider.complete(req, model="qwen3.7-plus"):
        print(chunk)


if __name__ == "__main__":
    asyncio.run(main())

"""第一次真实调用百炼的冒烟脚本（手动运行，花真钱：qwen-flash 一次 < 0.01 元）。

uv run python scripts/smoke_gateway.py
"""

import asyncio

from aegis.core.config import get_settings
from aegis.gateway.providers.openai_compat import OpenAICompatProvider
from aegis.gateway.schema import LLMRequest, Message, TextDelta


async def main() -> None:
    settings = get_settings()
    provider = OpenAICompatProvider(
        name="bailian",
        base_url=settings.dashscope_base_url,
        api_key=settings.dashscope_api_key.get_secret_value(),
    )
    req = LLMRequest(
        tier="fast",
        tenant_id="smoke",
        messages=[Message(role="user", content="用一句话说明你是什么模型。")],
    )
    async for chunk in provider.complete(req, model="qwen-flash"):
        if isinstance(chunk, TextDelta):
            print(chunk.text, end="", flush=True)  # 亲眼看 token 逐块到达
        else:
            print(f"\n{chunk}")


if __name__ == "__main__":
    asyncio.run(main())

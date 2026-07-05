"""通过完整网关的冒烟：只声明档位，模型由路由决定（需要本地 Redis 在跑）。

uv run python scripts/smoke_gateway.py
"""

import asyncio

from aegis.gateway.factory import build_gateway
from aegis.gateway.schema import LLMRequest, Message, TextDelta


async def main() -> None:
    gw = build_gateway()
    req = LLMRequest(
        tier="fast",
        tenant_id="smoke",
        messages=[Message(role="user", content="用一句话说明你是什么模型。")],
    )
    async for chunk in gw.complete(req):
        if isinstance(chunk, TextDelta):
            print(chunk.text, end="", flush=True)
        else:
            print(f"\n{chunk}")


if __name__ == "__main__":
    asyncio.run(main())

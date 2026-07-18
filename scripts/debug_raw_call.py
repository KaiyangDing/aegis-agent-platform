"""调试脚本：打印百炼原始响应的完整信封与正文（花真钱：一次 < 0.01 元）。

uv run python scripts/debug_raw_call.py
"""

import asyncio
import json

import httpx

from aegis.core.config import get_settings


async def main() -> None:
    s = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{s.dashscope_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {s.dashscope_api_key.get_secret_value()}"},
            json={"model": "qwen-plus", "messages": [{"role": "user", "content": "你好"}]},
        )
    print("== 状态行 ==")
    print(resp.status_code, resp.reason_phrase, resp.http_version)
    print("\n== 响应头（信封）==")
    for k, v in resp.headers.items():
        print(f"{k}: {v}")
    print(f"\n== 正文（{len(resp.content)} 字节）==")
    print(json.dumps(resp.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())


# == 状态行 ==
# 200 OK HTTP/1.1
#
# == 响应头（信封）==
# vary: Origin,Access-Control-Request-Method,Access-Control-Request-Headers, Accept-Encoding
# x-request-id: b2aa0fa6-b8ca-9173-8843-987b106bbcfa
# x-dashscope-call-gateway: true
# x-dashscope-finished: true
# x-dashscope-timeout: 3600
# content-type: application/json
# req-cost-time: 211
# req-arrive-time: 1783204498132
# resp-start-time: 1783204498344
# x-envoy-upstream-service-time: 211
# content-encoding: gzip
# date: Sat, 04 Jul 2026 22:34:57 GMT
# server: istio-envoy
# transfer-encoding: chunked
#
# == 正文（372 字节）==
# {
#   "choices": [
#     {
#       "finish_reason": "stop",
#       "index": 0,
#       "message": {
#         "content": "你好！有什么我可以帮你的吗？😊",
#         "role": "assistant"
#       }
#     }
#   ],
#   "created": 1783204498,
#   "id": "chatcmpl-b2aa0fa6-b8ca-9173-8843-987b106bbcfa",
#   "model": "qwen-flash",
#   "object": "chat.completion",
#   "usage": {
#     "completion_tokens": 9,
#     "prompt_tokens": 9,
#     "prompt_tokens_details": {
#       "cached_tokens": 0
#     },
#     "total_tokens": 18
#   }
# }

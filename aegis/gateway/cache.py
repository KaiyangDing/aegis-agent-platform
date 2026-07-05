"""精确缓存：完全相同的请求直接回放上次的 chunk 序列（零上游成本）。

key 三原则：
- tenant_id 明文前缀：跨租户绝不共享（评审确认过的头号缓存漏洞），且可按租户 SCAN 清理；
- 只哈希请求的语义本体（tier/messages/tools/temperature/max_tokens）——
  request_id/session_id 每次都变，混入则永不命中且静默烧钱；
- canonical JSON（sort_keys）：字段顺序差异不产生不同 key。

只缓存以 Stop 收尾的完整流；半截与失败绝不入库（缓存事故 = 可重放的事故）。
"""

import hashlib
import json

import redis.asyncio as aioredis

from aegis.gateway.schema import LLMChunk, LLMRequest, StopChunk, chunk_list_adapter


class ExactCache:
    def __init__(self, redis: aioredis.Redis, *, ttl_seconds: int = 300):
        self._r = redis
        self._ttl = ttl_seconds

    def _key(self, req: LLMRequest) -> str:
        essence = req.model_dump(exclude={"request_id", "session_id", "tenant_id"})
        blob = json.dumps(essence, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        return f"aegis:cache:{req.tenant_id}:{digest}"

    async def get(self, req: LLMRequest) -> list[LLMChunk] | None:
        raw = await self._r.get(self._key(req))
        if raw is None:
            return None
        return chunk_list_adapter.validate_json(raw)

    async def put(self, req: LLMRequest, chunks: list[LLMChunk]) -> None:
        if not chunks or not isinstance(chunks[-1], StopChunk):
            return  # 防御：只收完整流，半截不入库
        await self._r.set(self._key(req), chunk_list_adapter.dump_json(chunks), ex=self._ttl)

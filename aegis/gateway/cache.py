"""精确缓存：完全相同的请求直接回放上次的 chunk 序列（零上游成本）。

key 三原则：
- tenant_id 明文前缀：跨租户绝不共享（评审确认过的头号缓存漏洞），且可按租户 SCAN 清理；
- 只哈希请求的语义本体（tier/messages/tools/temperature/max_tokens）——
  request_id/session_id 每次都变，混入则永不命中且静默烧钱；
- canonical JSON（sort_keys）：字段顺序差异不产生不同 key。

key 前缀带 schema 版本号（v1）：chunk 结构升级后旧缓存天然全体 miss，
不会出现"新代码解析旧数据"的兼容地狱（审计加固 A）。

入库标准（审计加固 A 收紧）：以 Stop 收尾 且 含实质内容（至少一个 TextDelta/ToolCallChunk）。
半截、失败、空洞流绝不入库——缓存事故 = 可重放的事故。
脏数据自愈：读到解析不了的条目当场删除、按 miss 处理。
"""

import hashlib
import json

import redis.asyncio as aioredis
from pydantic import ValidationError

from aegis.gateway.schema import (
    LLMChunk,
    LLMRequest,
    StopChunk,
    TextDelta,
    ToolCallChunk,
    chunk_list_adapter,
)


class ExactCache:
    def __init__(self, redis: aioredis.Redis, *, ttl_seconds: int = 300):
        self._r = redis
        self._ttl = ttl_seconds

    def _key(self, req: LLMRequest) -> str:
        essence = req.model_dump(exclude={"request_id", "session_id", "tenant_id", "deadline_s"})
        blob = json.dumps(essence, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        return f"aegis:cache:v1:{req.tenant_id}:{digest}"

    async def get(self, req: LLMRequest) -> list[LLMChunk] | None:
        key = self._key(req)
        raw = await self._r.get(key)
        if raw is None:
            return None
        try:
            return chunk_list_adapter.validate_json(raw)
        except ValidationError:
            await self._r.delete(key)  # 自愈：脏条目当场清除，本次按 miss 处理
            return None

    async def put(self, req: LLMRequest, chunks: list[LLMChunk]) -> None:
        complete = bool(chunks) and isinstance(chunks[-1], StopChunk)
        has_substance = any(isinstance(c, TextDelta | ToolCallChunk) for c in chunks)
        if not complete or not has_substance:
            return  # 防御：半截/空洞流不入库
        await self._r.set(self._key(req), chunk_list_adapter.dump_json(chunks), ex=self._ttl)

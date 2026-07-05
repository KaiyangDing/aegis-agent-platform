from aegis.gateway.cache import ExactCache
from aegis.gateway.schema import (
    LLMRequest,
    Message,
    StopChunk,
    TextDelta,
    ToolCall,
    ToolCallChunk,
    UsageChunk,
)

CHUNKS = [
    TextDelta(text="你好"),
    ToolCallChunk(tool_call=ToolCall(id="c1", name="f", arguments_json="{}")),
    UsageChunk(model="m", prompt_tokens=3, completion_tokens=4),
    StopChunk(reason="end_turn"),
]


def req(tenant: str = "t1", content: str = "你好", **kw) -> LLMRequest:
    return LLMRequest(
        tier="fast", tenant_id=tenant, messages=[Message(role="user", content=content)], **kw
    )


class KeyProbe(ExactCache):
    """只为暴露 _key 做断言——不碰 Redis 的纯 key 测试。"""

    def __init__(self):  # noqa: D107 —— 故意不要 redis 依赖
        self._ttl = 0

    def key(self, r: LLMRequest) -> str:
        return self._key(r)


def test_key_ignores_volatile_ids():
    probe = KeyProbe()
    assert probe.key(req()) == probe.key(req(session_id="s-другой"))
    # request_id 每次自动生成都不同——两次构造 key 依然相同
    assert probe.key(req()) == probe.key(req())


def test_key_has_tenant_prefix_and_isolates_tenants():
    probe = KeyProbe()
    k1, k2 = probe.key(req(tenant="tA")), probe.key(req(tenant="tB"))
    assert k1.startswith("aegis:cache:tA:")
    assert k1.split(":")[-1] != k2.split(":")[-1] or k1 != k2  # 前缀已隔离


def test_key_changes_with_semantics():
    probe = KeyProbe()
    assert probe.key(req(content="A")) != probe.key(req(content="B"))
    assert probe.key(req()) != probe.key(req(temperature=0.7))


async def test_roundtrip_preserves_all_chunk_types(r):
    cache = ExactCache(r, ttl_seconds=60)
    await cache.put(req(), CHUNKS)
    assert await cache.get(req()) == CHUNKS  # 类型与内容逐一还原——M1.1 往返设计的红利


async def test_miss_returns_none(r):
    cache = ExactCache(r, ttl_seconds=60)
    assert await cache.get(req(content="从没问过的问题")) is None


async def test_ttl_is_applied(r):
    cache = ExactCache(r, ttl_seconds=60)
    await cache.put(req(content="ttl 检查"), CHUNKS)
    ttl = await r.ttl(cache._key(req(content="ttl 检查")))
    assert 0 < ttl <= 60


async def test_incomplete_stream_never_stored(r):
    cache = ExactCache(r, ttl_seconds=60)
    await cache.put(req(content="半截"), CHUNKS[:2])  # 没有 Stop 收尾
    assert await cache.get(req(content="半截")) is None

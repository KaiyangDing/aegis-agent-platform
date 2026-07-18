"""composition root 的装配冒烟测试（离线：redis/httpx 都是懒连接，构造不碰网络）。

守的是"配置字段 → 组件参数"的搬运正确性：tenant/provider 速率写反、
cache 开关判断写反这类错误，其他测试全用替身根本看不见（审计加固 C）。
"""

import pytest

from aegis.core.config import get_settings
from aegis.gateway.cache import ExactCache
from aegis.gateway.factory import build_gateway
from aegis.gateway.router import Candidate


@pytest.fixture
def fresh_settings(monkeypatch):
    get_settings.cache_clear()  # lru_cache 单例：换环境变量前后都要清
    yield monkeypatch
    get_settings.cache_clear()


def test_build_gateway_wires_settings_end_to_end(fresh_settings):
    m = fresh_settings
    m.setenv("PROVIDER_RATE", "3.5")
    m.setenv("TENANT_RATE", "1.5")
    m.setenv("CACHE_TTL_SECONDS", "0")
    m.setenv("FAULT_INJECTION_RATE", "0.3")
    m.setenv("FAULT_INJECTION_TARGETS", '["bailian:qwen-plus"]')
    gw = build_gateway()
    assert gw._cache is None  # ttl=0 → 缓存关闭
    assert gw._limits.provider_rate == 3.5
    assert gw._limits.tenant_rate == 1.5  # 两个维度没有被搬运时调换
    assert gw._fault_targets == frozenset({"bailian:qwen-plus"})
    assert set(gw._routes) == {"fast", "standard", "strong"}
    # 2026-07-17 模型池重构（幻影 glm5.2 移除+充值解锁）：fast 首选 qwen-flash——钉住 config 默认路由的搬运
    assert gw._routes["fast"][0] == Candidate("bailian", "qwen-flash")


def test_build_gateway_cache_on_when_ttl_positive(fresh_settings):
    fresh_settings.setenv("CACHE_TTL_SECONDS", "60")
    gw = build_gateway()
    assert isinstance(gw._cache, ExactCache)

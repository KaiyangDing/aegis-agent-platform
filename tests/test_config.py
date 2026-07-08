from typing import Any

import pytest
from pydantic import ValidationError

from aegis.core.config import Settings, get_settings


def make_settings(**kw: Any) -> Settings:
    """_env_file=None 禁用 .env 读取——否则本地 .env 会污染"默认值"断言。

    type: ignore 的原因：pydantic v2 元类带 @dataclass_transform，mypy 按字段为
    Settings 合成 __init__，盖掉了 BaseSettings 真实存在的 _env_file 参数——
    运行时合法，纯类型缝隙。全仓类型门只豁免这一处。
    """
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


def test_defaults_without_env_file():
    s = make_settings()
    assert s.app_env == "dev"
    assert s.database_url.startswith("postgresql+asyncpg://")


def test_env_var_overrides_default(monkeypatch):
    # monkeypatch 是 pytest 内置夹具：设的环境变量在本测试结束后自动还原
    monkeypatch.setenv("APP_ENV", "prod")
    s = make_settings()
    assert s.app_env == "prod"


def test_secret_never_leaks_in_repr(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-super-secret")
    s = make_settings()
    assert "sk-super-secret" not in repr(s)  # 泄漏防线本身也要有测试
    assert s.dashscope_api_key.get_secret_value() == "sk-super-secret"


def test_get_settings_is_singleton():
    assert get_settings() is get_settings()


def test_rate_limits_must_be_positive():
    # 审计加固 A：速率写成 0 会让 Lua 的 capacity/rate 溢出——环境变量写错要在启动时炸
    with pytest.raises(ValidationError):
        make_settings(provider_rate=0)


def test_prod_forbids_fault_injection():
    # 实验开关误带上生产：启动即炸，不在凌晨的真实流量里炸
    with pytest.raises(ValidationError):
        make_settings(app_env="prod", fault_injection_rate=0.3)


def test_staging_and_dev_allow_fault_injection():
    s = make_settings(app_env="dev", fault_injection_rate=0.3)
    assert s.fault_injection_rate == 0.3

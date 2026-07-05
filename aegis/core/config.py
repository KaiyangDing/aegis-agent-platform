from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，唯一事实源。读取优先级：环境变量 > .env 文件 > 字段默认值。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["dev", "staging", "prod"] = "dev"

    # 密钥一律 SecretStr：repr/日志显示 **********，取真值必须 .get_secret_value()。
    # 默认空值是刻意的——CI 和不碰真实 API 的测试无需配 key，M1 在真正调用前校验非空。
    dashscope_api_key: SecretStr = SecretStr("")
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_base_url: str = "https://api.anthropic.com"

    # 基础设施连接串，默认值就是下一步 docker-compose 的本地地址
    database_url: str = "postgresql+asyncpg://aegis:aegis@localhost:5432/aegis"
    redis_url: str = "redis://localhost:6379/0"

    # —— 网关路由与限流（M1.9）——
    # 档位 → 候选链（"provider:model"，按序 fallback）。环境变量可用 JSON 覆盖。
    model_routes: dict[str, list[str]] = {
        "fast": ["bailian:qwen-flash", "bailian:qwen-turbo"],
        "standard": ["bailian:qwen-plus", "bailian:deepseek-v3"],
        "strong": ["bailian:qwen-max", "bailian:deepseek-v3"],
    }
    provider_rate: float = 8.0  # 每供应商出站 QPS（演示值，压测后调）
    provider_burst: float = 16.0
    tenant_rate: float = 5.0  # 每租户出站 QPS
    tenant_burst: float = 10.0
    limiter_max_wait: float = 10.0  # 限流排队预算
    fault_injection_rate: float = 0.0  # 故障注入概率（0=关闭）
    fault_injection_targets: list[str] = []  # 注入目标，如 ["bailian:qwen-plus"]


@lru_cache
def get_settings() -> Settings:
    """进程内单例。测试想要干净实例时直接构造 Settings()，绕过缓存。"""
    return Settings()

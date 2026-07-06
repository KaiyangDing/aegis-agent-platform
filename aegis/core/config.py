from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
        # fast 链末位升档到 qwen-plus：兑现 02 §4"fast 耗尽可升档"的承诺（审计加固 A）
        "fast": ["bailian:qwen-flash", "bailian:qwen-turbo", "bailian:qwen-plus"],
        "standard": ["bailian:qwen-plus", "bailian:deepseek-v3"],
        "strong": ["bailian:qwen-max", "bailian:deepseek-v3"],
    }
    # gt=0：速率写成 0 会让 Lua 里 capacity/rate 溢出，环境变量写错要在启动时炸
    provider_rate: float = Field(default=8.0, gt=0)  # 每供应商出站 QPS（演示值，压测后调）
    provider_burst: float = Field(default=16.0, gt=0)
    tenant_rate: float = Field(default=5.0, gt=0)  # 每租户出站 QPS
    tenant_burst: float = Field(default=10.0, gt=0)
    limiter_max_wait: float = 10.0  # 限流排队预算
    replica_count: int = Field(default=1, ge=1)  # 部署副本数：Redis 降级时本地配额=全局/副本数
    cache_ttl_seconds: int = 300  # 精确缓存 TTL；0 = 关闭缓存
    # 模型单价（元/千 token，[输入, 输出]）——演示值，以百炼价目页为准；调价改这里不改代码
    model_prices: dict[str, list[float]] = {
        "qwen-flash": [0.00015, 0.0015],
        "qwen-turbo": [0.0003, 0.0006],
        "qwen-plus": [0.0008, 0.002],
        "qwen-max": [0.0024, 0.0096],
        "deepseek-v3": [0.002, 0.008],
    }
    tenant_monthly_token_budget: int = 0  # 租户月度 token 预算；0=关闭，超额抛 BudgetExceeded
    fault_injection_rate: float = 0.0  # 故障注入概率（0=关闭）
    fault_injection_targets: list[str] = []  # 注入目标，如 ["bailian:qwen-plus"]

    @model_validator(mode="after")
    def _no_fault_injection_in_prod(self) -> "Settings":
        # 实验开关误带上生产 = 对真实流量随机注 5xx，且故障与真实上游故障不可区分。
        # 与 parse_routes 同一哲学：配置错误在启动时炸，不在凌晨的流量里炸（审计加固 B）
        if self.app_env == "prod" and self.fault_injection_rate > 0:
            raise ValueError("prod 环境禁止开启故障注入（fault_injection_rate 必须为 0）")
        return self


@lru_cache
def get_settings() -> Settings:
    """进程内单例。测试想要干净实例时直接构造 Settings()，绕过缓存。"""
    return Settings()

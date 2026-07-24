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
        # 2026-07-17 模型池重构：充值解锁 classic 梯队，按"便宜优先"分层；幻影 glm5.2 移除
        # ——07-16 写入的容灾候选实测 404 model_not_found（入池未实测的代价，三档 fallback
        # 断链两日）。入池三验纪律见 06 §5：存在性 / 思考默认态 / 关思考参数接受性。
        # qwen3.7-max 默认思考，已由适配器统一 enable_thinking:false（openai_compat）
        "fast": ["bailian:qwen-flash", "bailian:qwen-turbo"],
        "standard": ["bailian:qwen-plus", "bailian:qwen-turbo"],
        "strong": ["bailian:qwen3.7-max", "bailian:qwen-plus"],
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
        "qwen-flash": [0.00015, 0.0015],  # 演示值——务必按百炼价目页更新（#28）
        "qwen-turbo": [0.0003, 0.0006],  # 演示值——同上
        "qwen-plus": [0.0008, 0.002],  # 演示值——同上
        "qwen3.7-max": [0.0024, 0.0096],  # 演示值——同上
        "qwen3.7-plus": [0.0008, 0.002],  # 演示值——已退出路由，保留供历史账本行核对
    }
    tenant_monthly_token_budget: int = 0  # 租户月度 token 预算；0=关闭，超额抛 BudgetExceeded
    request_token_budget: int = 0  # 单请求 token 预算（估算口径）；0=关闭（§10.1 #1，三级预算 L1 级）
    fault_injection_rate: float = 0.0  # 故障注入概率（0=关闭）
    fault_injection_targets: list[str] = []  # 注入目标，如 ["bailian:qwen-plus"]
    fault_injection_mode: Literal["error", "hang", "midstream"] = "error"  # 注入形态（评审 C1 补挂起/断流盲区）

    # —— 恢复调度（M2.10）——
    lease_ttl_s: float = Field(default=60.0, gt=0)  # 会话租约时长（P1：TTL=3×续租间隔，容两次续租失败）
    lease_renew_interval_s: float = Field(default=20.0, gt=0)  # loop 续租间隔
    reaper_interval_s: float = Field(default=30.0, gt=0)  # beat 扫描周期（P2：发现延迟上界≈TTL+周期=90s）
    recovery_limit: int = Field(default=3, ge=1)  # C9：恢复次数上限（P3）

    # —— API 认证（M3.1，P2 拍板：HS256 双密钥窗）——
    jwt_secret: SecretStr = SecretStr("")  # 签发/验签密钥；空=API 认证不可用（auth.py fail-loud）
    jwt_secret_previous: SecretStr = SecretStr("")  # 轮换窗旧钥：验签先 current 再 previous，轮换不踢在线用户
    jwt_user_ttl_s: int = Field(default=7200, gt=0)  # 终端用户 token 时长 2h
    jwt_staff_ttl_s: int = Field(default=28800, gt=0)  # 坐席/管理员 token 时长 8h

    # —— API 入站（M3.2）——
    inbound_rate: float = Field(default=2.0, gt=0)  # 每租户入站 QPS（演示值；与 L1 出站限流分工——02 §1）
    inbound_burst: float = Field(default=5.0, gt=0)

    @model_validator(mode="after")
    def _no_fault_injection_in_prod(self) -> "Settings":
        # 实验开关误带上生产 = 对真实流量随机注 5xx，且故障与真实上游故障不可区分。
        # 与 parse_routes 同一哲学：配置错误在启动时炸，不在凌晨的流量里炸（审计加固 B）
        if self.app_env == "prod" and self.fault_injection_rate > 0:
            raise ValueError("prod 环境禁止开启故障注入（fault_injection_rate 必须为 0）")
        return self

    @model_validator(mode="after")
    def _lease_renew_shorter_than_ttl(self) -> "Settings":
        # 间隔 ≥ TTL 意味着租约必然在两次心跳之间过期——配置错误启动时炸（审计加固 B 哲学）
        if self.lease_renew_interval_s >= self.lease_ttl_s:
            raise ValueError("lease_renew_interval_s 必须小于 lease_ttl_s（否则租约必然过期）")
        return self


@lru_cache
def get_settings() -> Settings:
    """进程内单例。测试想要干净实例时直接构造 Settings()，绕过缓存。"""
    return Settings()

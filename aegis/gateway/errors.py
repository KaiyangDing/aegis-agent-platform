"""网关错误分类。

分类的意义在 M1.6 兑现：重试白名单按异常类型判断，不靠猜字符串。
异常携带排障上下文（供应商/重试提示），但绝不携带请求内容等敏感信息。
"""


class GatewayError(Exception):
    """网关所有错误的基类。"""


class ProviderError(GatewayError):
    """某个供应商调用失败的基类。"""

    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class RateLimitedError(ProviderError):
    """429 被限流。retry_after 取自响应头，M1.6 的退避要优先读它。"""

    def __init__(self, provider: str, message: str, retry_after: float | None = None):
        super().__init__(provider, message)
        self.retry_after = retry_after


class ProviderTimeoutError(ProviderError):
    """连接或读取超时。注意：请求可能已在上游执行（重复计费风险，M1.6 讨论）。"""


class ProviderServerError(ProviderError):
    """502/503/504 —— 上游故障，可重试。"""


class BadRequestError(ProviderError):
    """4xx（除 429/401/403）—— 请求本身有问题，重试无意义。"""


class AuthError(ProviderError):
    """401/403 —— 该修配置，不该重试。"""


class GatewayExhausted(GatewayError):
    """重试与 fallback 全部用尽。L2 只会见到它和 BudgetExceeded（契约 03 §7）。"""


class BudgetExceeded(GatewayError):
    """token 预算闸门触发（M1.11 起逐步接入）。"""

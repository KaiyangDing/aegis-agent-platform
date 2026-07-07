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


class GatewayOverloadedError(GatewayError):
    """本地连接池排队超时——是我们自己过载，不是上游故障。

    三个"不"（审计加固 A）：不记熔断账（供应商无辜）、不重试（重试加剧池争抢）、
    不换路（所有候选共用同一个连接池，换了也白换）。
    """


class GatewayExhausted(GatewayError):
    """重试与 fallback 全部用尽（发生在首块之前，未产生任何输出）。

    契约（03 §7，评审 C6 升级为六类）：L2 可见的网关异常——
    请求级（首块前，可整体降级）：GatewayExhausted / BudgetExceeded /
        TenantQuotaExceeded / GatewayOverloadedError；
    请求级（确定性拒绝，不降级）：GatewayRejected；
    流级（首块后，进恢复语义）：GatewayStreamInterrupted。
    ProviderError 家族永远不穿出网关。
    """


class BudgetExceeded(GatewayError):
    """token 预算闸门触发（M1.11 起逐步接入）。"""


class TenantQuotaExceeded(GatewayError):
    """租户级出站配额耗尽。换供应商无解（配额跟租户走），调用方应直接降级或提示。"""


class GatewayRejected(GatewayError):
    """全部候选均为确定性拒绝（Auth/BadRequest），且无任何暂时性因素掺入（评审 C6）。

    这是"我们自己的配置/协议 bug"信号——错的 API key、非法的请求转换。
    与 GatewayExhausted 的分野：Exhausted = 暂时不可用，降级合理；
    Rejected = 重试和降级都无意义，L2 不走兜底话术（那会把 bug 藏起来），
    终止 run 并报配置/协议错误（终止原因 gateway_rejected，M2.2 枚举留位）。
    """


class GatewayStreamInterrupted(GatewayError):
    """流已开始后中断：消费方已收到部分 chunk，且绝不会被换路重放（红线一）。

    L2 的"半截 llm_call"恢复语义（03 §5：作废重发 + 前端消息重置帧）以捕获
    本异常为入口；原始死因保留在 __cause__ 上。
    """

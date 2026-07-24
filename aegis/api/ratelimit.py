"""入站限流依赖（M3.2，02 §1 两级分工的入站半边；D6 复用 L1 令牌桶原语）。

与出站的分工：出站限流保护供应商（可排队 max_wait>0）；入站保护自己（即问即答，
超限 429 + Retry-After 提示——排队会把压力囤在自家线程上）。scope 前缀
inbound:{tenant_id}，与出站 tenant:{id}/provider:{id} 同一命名族、账本互不相干。
"""

# 本模块刻意不用 `from __future__ import annotations`：rate_limited 内层依赖的
# Annotated[..., Depends(role_dep)] 引用闭包变量——future 模式下注解成字符串，
# FastAPI 以模块全局名字空间反解时看不见闭包名，该参数退化为必填 query（全量 422）。
# 注解按 def 时求值（本形态）才能把闭包里的 Depends 捕进元数据。auth.py 不受此限
# （其内层注解引用的 current_principal 是模块全局名）。

import math
from collections.abc import Awaitable, Callable
from typing import Annotated, Protocol

from fastapi import Depends, HTTPException, Request, status

from aegis.api.auth import Principal


class InboundLimiterLike(Protocol):
    """按形状声明：生产=gateway.ratelimit.RateLimiter（try_take 返回 (是否放行, 建议等待秒)），
    测试注入可编程桩——与 SessionFactory 别名同款哲学。"""

    async def try_take(self, scope: str, rate: float, capacity: float, cost: float = 1.0) -> tuple[bool, float]: ...


def rate_limited(role_dep: Callable[..., Awaitable[Principal]]) -> Callable[..., Awaitable[Principal]]:
    """依赖工厂：在角色门之后加租户维度入站限流——链序 401→403→429 由嵌套 Depends 保证。"""

    async def dependency(request: Request, principal: Annotated[Principal, Depends(role_dep)]) -> Principal:
        settings = request.app.state.settings
        limiter: InboundLimiterLike = request.app.state.limiter
        ok, wait = await limiter.try_take(
            f"inbound:{principal.tenant_id}", settings.inbound_rate, settings.inbound_burst
        )
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="请求过于频繁，请稍后再试",
                headers={"Retry-After": str(max(1, math.ceil(wait)))},
            )
        return principal

    return dependency

"""五工具共用底座（M3.7 交付③）：归属校验查单 + #43 写请求契约。

计划文件清单外的第 6 个文件（偏差登记）：归属校验与 #43 条款是五工具的共同
不变量，复制五份=漂移面——话术改一处漏四处、契约条款各自演化。
"""

from __future__ import annotations

from typing import Any

import httpx

from aegis.apps.support.mock_backend.client import mock_client
from aegis.runtime.tools import ToolContext

DENIED_TEXT = "订单不存在或无权操作"
"""对抗③统一话术：他人订单/跨租户/不存在三种失败不区分——泄露"存在但无权"
就是泄露他人订单号的有效性（02 §7.2 第 2 层）。"""


async def fetch_owned_order(ctx: ToolContext, order_id: str) -> dict[str, Any] | None:
    """查单 + 归属校验（fail-closed）：任何一环不过一律 None，调用方回统一话术。

    mock 侧 WHERE tenant_id 已滤跨租户（404）；这里再显式双比对 tenant+user——
    归属判定权在工具（02 §7.2 原文 `order.user_id == ctx.user_id`），mock 只交出行。
    身份全部取自 ctx（运行时注入，模型不可控），谓词里没有任何 LLM 参数。
    """
    resp = await mock_client().get(f"/orders/{order_id}", params={"tenant_id": ctx.tenant_id})
    if resp.status_code == 404:
        return None
    # M4.7 ㊱(55) 复核声明：raise_for_status 把协议错（4xx，重试永远失败）与可重试故障
    # （503）合流成同一种 ERROR——**当前不可达**：mock 读端点只产 200/404/503（404 已
    # 在上面消化）。前提是 mock 形态；换真实下游（v2/真实化）时读侧必须补 #43 同款
    # 的错误分层，且"直读 mock_orders"的三条理由（(55)）届时全部反转，一并复核。
    resp.raise_for_status()  # 503 等非预期状态：裸抛 → executor ERROR（读语义可安全改道）
    order: dict[str, Any] = resp.json()
    if order["tenant_id"] != ctx.tenant_id or order["user_id"] != ctx.user_id:
        return None
    return order


async def post_write(path: str, *, json_body: dict[str, Any], idempotency_key: str) -> httpx.Response:
    """写请求单点：幂等键接线（#6）+ #43 传输契约（拍板Ⅰ）。

    发出前/发出后分界：连接未建立（ConnectError/ConnectTimeout）=请求没到对端、
    零副作用——原样上抛走 executor 普通 ERROR，模型可改道；其余传输/协议错误
    发生在发出后，物理上与超时同样"结果不明"——转 TimeoutError 交 X1 现成路径
    （executor.py:188 同一 except 分支）→ RESULT_UNKNOWN + 封死重试话术。
    """
    try:
        return await mock_client().post(path, json=json_body, headers={"Idempotency-Key": idempotency_key})
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise
    except httpx.HTTPError as e:
        raise TimeoutError(f"写请求发出后传输异常，结果不明：{type(e).__name__}") from e

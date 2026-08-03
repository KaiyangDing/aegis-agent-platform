"""M3.7 交付③：五工具契约面——声明清单（#38 进 CI）/schema 快照/阈值边界。

不跑任何 mock 调用：这里钉的是 ToolDef 说明书本身——名字、读写、闸门三元组、
参数面（ctx 与身份参数绝不暴露给模型）、risk_policy 谓词的数值边界。
"""

from __future__ import annotations

from typing import Any

from aegis.apps.support.tools.coupons import coupon_grant
from aegis.apps.support.tools.logistics import logistics_query
from aegis.apps.support.tools.orders import order_query
from aegis.apps.support.tools.refunds import refund_apply
from aegis.apps.support.tools.tickets import ticket_create
from aegis.runtime.tools import SideEffect, ToolDef

_FIVE: tuple[ToolDef, ...] = (order_query, logistics_query, ticket_create, refund_apply, coupon_grant)


def test_declarations_ledger() -> None:
    """#38 的 CI 化：五工具逐个点名读写与闸门声明——防"批量豁免糊弄过防呆"的省事写法。"""
    ledger = {t.name: (t.side_effect, t.risk_policy is not None, t.risk_exempt) for t in _FIVE}
    assert ledger == {
        "order_query": (SideEffect.READ, False, False),
        "logistics_query": (SideEffect.READ, False, False),
        "ticket_create": (SideEffect.WRITE, False, True),  # 低危写显式豁免（C15 留档）
        "refund_apply": (SideEffect.WRITE, True, False),
        "coupon_grant": (SideEffect.WRITE, True, False),
    }


def test_ctx_and_identity_never_in_schema() -> None:
    """身份只从 ctx 来（§4.7 陷阱 4）：ctx 被装饰器剔除，业务参数里也绝不再开 user_id/tenant_id 口子。"""
    for t in _FIVE:
        props = set(t.parameters_schema["properties"])
        assert "ctx" not in props
        assert "user_id" not in props
        assert "tenant_id" not in props


def test_schema_params_are_expected() -> None:
    """参数面快照：LLM 可控的只有业务查询条件。"""
    assert set(order_query.parameters_schema["properties"]) == {"order_id"}
    assert set(logistics_query.parameters_schema["properties"]) == {"order_id"}
    assert set(ticket_create.parameters_schema["properties"]) == {"title", "detail"}
    assert ticket_create.parameters_schema["required"] == ["title"]  # detail 有默认值
    assert set(refund_apply.parameters_schema["properties"]) == {"order_id", "amount"}
    assert set(coupon_grant.parameters_schema["properties"]) == {"order_id", "amount"}


def _risk(tool: ToolDef, config: dict[str, Any], **kw: Any) -> bool:
    assert tool.args_model is not None and tool.risk_policy is not None
    return tool.risk_policy(tool.args_model(**kw), config)


def test_refund_threshold_boundary_200() -> None:
    """阈值语义=严格大于（§4.7 测试蓝图点名 200/200.01）：等于阈值不挂审批。

    缺省值语义见 test_refund_threshold_default_is_fail_closed（M4.0② ㊲ 改判）。
    """
    cfg = {"approval_threshold": 200}
    assert _risk(refund_apply, cfg, order_id="o", amount=200.0) is False
    assert _risk(refund_apply, cfg, order_id="o", amount=200.01) is True


def test_refund_threshold_default_is_fail_closed() -> None:
    """M4.0② ㊲：租户 config 缺 approval_threshold → 任意正金额都挂审批。

    改判前缺省 200 是 fail-OPEN：新租户漏配 = 200 元以下静默直退（无审批无告警无痕迹），
    与 00 §2.2「安全闸门 fail-closed」直接冲突，且同族 coupon_needs_approval 缺省 0
    是 fail-closed——同一类闸门对同一种故障（少一个键）行为相反，只有 coupon 那条被
    论证过。可达性不低：#21 治理路径下种子即初始化入口，漏配是现实运维事故。
    """
    assert _risk(refund_apply, {}, order_id="o", amount=0.01) is True
    assert _risk(refund_apply, {}, order_id="o", amount=199.99) is True
    # 显式配 0 与"缺键"同义，且不与"配了 200"混淆——缺省不再冒充一个业务阈值
    assert _risk(refund_apply, {"approval_threshold": 0}, order_id="o", amount=0.01) is True


def test_coupon_threshold_default_zero_fail_closed() -> None:
    """coupon_threshold 缺省 0=任意正面额都挂审批（安全闸门 fail-closed 缺省，§4.7 注）。"""
    assert _risk(coupon_grant, {}, order_id="o", amount=0.01) is True
    cfg = {"coupon_threshold": 50}
    assert _risk(coupon_grant, cfg, order_id="o", amount=50.0) is False
    assert _risk(coupon_grant, cfg, order_id="o", amount=50.01) is True

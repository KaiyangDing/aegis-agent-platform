"""M2.3 交付①：@tool 装饰器——签名即事实源、ctx 剔除、注册期防呆在 import 时爆炸。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aegis.runtime.tools import SideEffect, ToolContext, ToolDef, ToolRegistrationError, tool


def _make_order_query() -> ToolDef:
    @tool(side_effect=SideEffect.READ, timeout_s=15.0, retries=2)
    async def order_query(ctx: ToolContext, order_id: str, verbose: bool = False) -> dict:
        """按订单号查询订单状态。"""
        return {"order_id": order_id}

    return order_query


def test_decorator_returns_tooldef_with_metadata() -> None:
    t = _make_order_query()
    assert isinstance(t, ToolDef)
    assert t.name == "order_query"
    assert t.description == "按订单号查询订单状态。"
    assert t.side_effect is SideEffect.READ
    assert (t.timeout_s, t.retries) == (15.0, 2)
    assert t.risk_policy is None and t.risk_exempt is False


def test_schema_excludes_ctx_and_lists_params() -> None:
    """ctx 是运行时注入的身份——模型连它的存在都不许知道。"""
    t = _make_order_query()
    props = t.parameters_schema["properties"]
    assert "ctx" not in props
    assert set(props) == {"order_id", "verbose"}


def test_schema_required_optional_and_types() -> None:
    t = _make_order_query()
    schema = t.parameters_schema
    assert schema["required"] == ["order_id"]  # verbose 有默认值 → 可选
    assert schema["properties"]["order_id"]["type"] == "string"
    assert schema["properties"]["verbose"]["type"] == "boolean"
    assert schema["properties"]["verbose"]["default"] is False


def test_args_model_forbids_extra_params() -> None:
    """LLM 幻觉出的多余参数必须响亮拒绝——静默丢弃等于掩盖模型行为异常。"""
    t = _make_order_query()
    assert t.args_model is not None
    with pytest.raises(ValidationError):
        t.args_model.model_validate({"order_id": "1024", "bogus": 1})


def test_args_model_validates_happy_path() -> None:
    t = _make_order_query()
    assert t.args_model is not None
    args = t.args_model.model_validate({"order_id": "1024"})
    assert args.order_id == "1024"  # type: ignore[attr-defined]
    assert args.verbose is False  # type: ignore[attr-defined]


def test_name_override_and_empty_params() -> None:
    @tool(side_effect=SideEffect.READ, name="orders_lookup")
    async def whatever(ctx: ToolContext) -> None:
        """查订单。"""

    assert whatever.name == "orders_lookup"
    assert whatever.parameters_schema["properties"] == {}


def test_missing_ctx_rejected() -> None:
    with pytest.raises(ToolRegistrationError, match="ctx"):

        @tool(side_effect=SideEffect.READ)
        async def bad(order_id: str) -> None:
            """没 ctx。"""


def test_ctx_with_wrong_annotation_rejected() -> None:
    with pytest.raises(ToolRegistrationError, match="ctx"):

        @tool(side_effect=SideEffect.READ)
        async def bad(ctx: str, order_id: str) -> None:
            """ctx 注解不是 ToolContext。"""


def test_missing_annotation_rejected() -> None:
    with pytest.raises(ToolRegistrationError, match="order_id"):

        @tool(side_effect=SideEffect.READ)
        async def bad(ctx: ToolContext, order_id) -> None:
            """业务参数缺类型注解。"""


def test_varargs_rejected() -> None:
    with pytest.raises(ToolRegistrationError, match="args"):

        @tool(side_effect=SideEffect.READ)
        async def bad(ctx: ToolContext, *items: str) -> None:
            """可变位置参数。"""


def test_kwargs_rejected() -> None:
    with pytest.raises(ToolRegistrationError, match="kwargs"):

        @tool(side_effect=SideEffect.READ)
        async def bad(ctx: ToolContext, **extra: str) -> None:
            """可变关键字参数。"""


def test_empty_docstring_rejected() -> None:
    with pytest.raises(ToolRegistrationError, match="description"):

        @tool(side_effect=SideEffect.READ)
        async def bad(ctx: ToolContext) -> None: ...


def test_write_without_policy_rejected_at_decoration() -> None:
    """C15 从装饰器这扇门看：沉默的危险按钮在 import 时就炸。"""
    with pytest.raises(ToolRegistrationError, match="risk_policy"):

        @tool(side_effect=SideEffect.WRITE)
        async def refund(ctx: ToolContext, amount: int) -> None:
            """退款。"""

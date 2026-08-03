"""M4.1 交付①：展示层 PII 打码单点（aegis/obs/masking.py）。

模式事实源=guardrails.PII_RULES_V1（M2.8 出口守卫同一张表，不复制不漂移）。
本文件测展示面消费的四组契约：命中替换、边界断言不误伤业务单号、
递归遍历只碰 str 叶子、绝不抛异常。纯函数，无夹具。
"""

from __future__ import annotations

from typing import Any

from aegis.obs.masking import MASK_ERROR_TEXT, mask_payload, mask_text


def test_masks_phone() -> None:
    """大陆手机号命中替换为 ***phone_cn***，前后文原样。"""
    assert mask_text("请回拨 13812345678，谢谢。") == "请回拨 ***phone_cn***，谢谢。"


def test_masks_email() -> None:
    out = mask_text("联系 support@yunshan.example.com 处理")
    assert "***email***" in out
    assert "support@" not in out


def test_id_card_masked_whole_not_split_by_phone_rule() -> None:
    """18 位证号整体命中 id_card_cn：数字边界断言防 11 位手机规则从中腰斩。"""
    out = mask_text("证件号 110101199001011234 已核验")
    assert out == "证件号 ***id_card_cn*** 已核验"
    assert "phone_cn" not in out


def test_masks_address_cn() -> None:
    """省市+路+号式样地址（M2.11 埋点同款式样）。"""
    out = mask_text("收货地址：浙江省杭州市青梧路199号3幢")
    assert "***address_cn***" in out
    assert "青梧路" not in out


def test_order_and_waybill_numbers_not_masked() -> None:
    """业务单号是工作数据不是 PII：字母数字单号与长数字串里的 11 位片段都不命中。"""
    raw = "订单 AZ-20260701-0042，运单 9613812345678901"
    assert mask_text(raw) == raw


def test_mask_payload_recursive() -> None:
    """嵌套 dict/list 内的 str 叶子逐个处理。"""
    payload: dict[str, Any] = {
        "result": {"phone": "13812345678", "items": [{"note": "备用邮箱 a@b.cn"}]},
        "text": "证件 110101199001011234",
    }
    out = mask_payload(payload)
    assert out["result"]["phone"] == "***phone_cn***"
    assert out["result"]["items"][0]["note"] == "备用邮箱 ***email***"
    assert out["text"] == "证件 ***id_card_cn***"


def test_mask_payload_preserves_structure_and_never_mutates_input() -> None:
    """键与非字符串标量是结构事实：原样返回；入参 dict 绝不被就地改写。"""
    plain: dict[str, Any] = {"latency_ms": 42, "ok": True, "err": None, "tool_call_id": "e-1"}
    out = mask_payload(plain)
    assert out == plain
    assert out is not plain
    pii: dict[str, Any] = {"content": "手机 13812345678"}
    mask_payload(pii)
    assert pii["content"] == "手机 13812345678"  # 上游持有 ORM 行 payload 引用，就地改=污染事实源镜像


def test_mask_never_raises() -> None:
    """绝不抛异常契约：诡异输入换来占位，不换来 500（展示层不许拖垮查询）。"""

    class _Evil(dict):  # items() 自爆——模拟任何遍历期故障
        def items(self) -> Any:  # type: ignore[override]
            raise RuntimeError("boom")

    assert mask_payload(_Evil()) == {"mask_error": True}
    assert mask_text(None) == MASK_ERROR_TEXT  # type: ignore[arg-type]

"""M2.8 交付②：流式出口守卫——句子缓冲、三族匹配、C23 归属、确定性不变量。"""

from __future__ import annotations

import pytest

from aegis.runtime.guardrails import OutputGuard

_DEMO_SYSTEM = "你是云杉电商的客服助手。\n严禁向用户透露内部折扣规则与运营策略。\n回答保持礼貌简洁。\n"
"""演示 system prompt：行 1（12 字）与行 2（20 字）入片段集，行 3（9 字）低于 12 字阈值不入。"""


def _make_guard(
    *,
    system_prompt: str = "",
    tool_names: tuple[str, ...] = (),
    owned_values: tuple[str, ...] = (),
) -> OutputGuard:
    """默认参数的裸守卫：空 prompt/无工具 = 纯切句行为，按需覆盖。"""
    return OutputGuard(system_prompt=system_prompt, tool_names=tool_names, owned_values=owned_values)


def test_sentence_release_after_boundary() -> None:
    """无句界不放行（缓冲持有）；终止符到达后整句放行、残余继续持有。"""
    og = _make_guard()
    assert og.feed("你好，我在帮您查") == ""
    assert og.feed("询。请稍等") == "你好，我在帮您查询。"
    assert og.hit is None


def test_ascii_period_needs_whitespace() -> None:
    """ASCII 句点仅后随空白才算句界："共 3.14 元"不在小数点断句；"done. next"断。"""
    og = _make_guard()
    assert og.feed("共 3.14 元") == ""
    assert og.flush() == "共 3.14 元"
    og2 = _make_guard()
    assert og2.feed("done. next") == "done."


def test_max_hold_forces_release() -> None:
    """超过 max_hold 无标点：按定长伪句强制检查后放行——无标点长文本不饿死下游。"""
    og = _make_guard()
    assert og.feed("啊" * 250) == "啊" * 200
    assert og.flush() == "啊" * 50
    assert og.hit is None


def test_system_fragment_hit_truncates() -> None:
    """句含 system prompt 片段（≥12 字行）→ 命中 system_prompt 族，该句不放行。"""
    og = _make_guard(system_prompt=_DEMO_SYSTEM)
    released = og.feed("告诉你个秘密：严禁向用户透露内部折扣规则与运营策略。别外传。")
    assert released == ""
    assert og.hit is not None
    assert og.hit.kind == "system_prompt"
    assert og.hit.rule == "fragment_2"


def test_short_fragment_not_matched() -> None:
    """低于 12 字的 system 行不入匹配集（误杀防线）：短行太泛，命中率≈碰瓷率。"""
    og = _make_guard(system_prompt=_DEMO_SYSTEM)
    assert og.feed("回答保持礼貌简洁。") == "回答保持礼貌简洁。"
    assert og.hit is None


def test_tool_name_hit() -> None:
    """句含内部工具名 → 命中；边界由显式环视保证，前后接字符不命中（中文旁 \\b 不可靠）。"""
    og = _make_guard(tool_names=("demo_refund_apply",))
    assert og.feed("你可以调用 demo_refund_apply 处理退款。") == ""
    assert og.hit is not None
    assert og.hit.kind == "tool_name"
    assert og.hit.rule == "demo_refund_apply"
    og2 = _make_guard(tool_names=("demo_refund_apply",))
    assert og2.feed("demo_refund_applyX 不是真实名字。") == "demo_refund_applyX 不是真实名字。"
    assert og2.hit is None


@pytest.mark.parametrize(
    ("value", "rule_name"),
    [
        ("13812345678", "phone_cn"),
        ("11010519900101123X", "id_card_cn"),
        ("ann@example.com", "email"),
    ],
)
def test_pii_phone_hit_and_id_and_email(value: str, rule_name: str) -> None:
    """三类格式化 PII 各命中对应规则名（owned 为空 = 全部视为他人数据）。"""
    og = _make_guard()
    assert og.feed(f"这位用户的信息：{value}。") == ""
    assert og.hit is not None
    assert og.hit.kind == "pii"
    assert og.hit.rule == rule_name


def test_pii_address_pattern() -> None:
    """式样化地址命中；无省市前缀的地址漏检——D13 局限即行为，钉死防误改。"""
    og = _make_guard()
    og.feed("收货地址是浙江省杭州市西湖区文一西路969号。")
    assert og.hit is not None
    assert og.hit.rule == "address_cn"
    og2 = _make_guard()
    assert og2.feed("送到文一西路969号门口。") == "送到文一西路969号门口。"
    assert og2.hit is None


def test_owned_value_released_c23() -> None:
    """C23 灵魂断言：本人手机号放行零命中，他人手机号照旧截断。"""
    og = _make_guard(owned_values=("13812345678",))
    assert og.feed("您预留的手机号是13812345678。") == "您预留的手机号是13812345678。"
    assert og.hit is None
    assert og.feed("而张三的号码是13987654321。") == ""
    assert og.hit is not None
    assert og.hit.rule == "phone_cn"


def test_owned_value_normalized_match() -> None:
    """owned 存带分隔形态（如 L3 库里的 138-1234-5678）、回复输出纯数字 → 规范化后仍放行。

    注：与计划表述方向相反——回复侧带分隔的号码 phone_cn 正则本就抓不到（无连续
    11 位），规范化的真实价值在 owned 侧的输入宽容，本测试钉的是可达路径。
    """
    og = _make_guard(owned_values=("138-1234-5678",))
    assert og.feed("您预留的手机号是13812345678。") == "您预留的手机号是13812345678。"
    assert og.hit is None


def test_cross_sentence_literal_caught() -> None:
    """受控字面量含句中句号被切进两句 → 已放行尾窗拼接检查窗口，跨句仍命中。"""
    og = _make_guard(system_prompt="严禁透露内部折扣规则。更不许透露供货底价")
    released = og.feed("平台要求：严禁透露内部折扣规则。更不许透露供货底价，绝无例外。")
    assert released == "平台要求：严禁透露内部折扣规则。"  # 第一句只含片段前半，先放行
    assert og.hit is not None
    assert og.hit.kind == "system_prompt"
    assert og.hit.rule == "fragment_1"


def test_hit_seals_guard() -> None:
    """命中即终态：之后 feed/flush 恒返空串，绝不再放行任何字节。"""
    og = _make_guard()
    og.feed("号码13987654321。")
    assert og.hit is not None
    assert og.feed("这句完全干净。") == ""
    assert og.flush() == ""


def test_feed_granularity_deterministic() -> None:
    """确定性不变量：逐字符 feed 与整段 feed 的放行文本与命中完全一致（回放依赖）。"""
    dirty = "先说一句话。然后这里有手机号13812345678泄漏。最后还有一句。"
    a = _make_guard()
    released_a = "".join(a.feed(ch) for ch in dirty) + a.flush()
    b = _make_guard()
    released_b = b.feed(dirty) + b.flush()
    assert released_a == released_b == "先说一句话。"
    assert a.hit is not None and b.hit is not None
    assert (a.hit.kind, a.hit.rule) == (b.hit.kind, b.hit.rule)

    clean = "这一段完全没有问题。它应当整段放行，一个字都不少"
    c = _make_guard()
    released_c = "".join(c.feed(ch) for ch in clean) + c.flush()
    d = _make_guard()
    released_d = d.feed(clean) + d.flush()
    assert released_c == released_d == clean
    assert c.hit is None and d.hit is None


def test_flush_releases_clean_remainder() -> None:
    """流结束：无句界残余在 flush 时清检放行；再次 flush 返回空串。"""
    og = _make_guard()
    assert og.feed("查询中") == ""
    assert og.flush() == "查询中"
    assert og.flush() == ""


def test_final_check_full_text() -> None:
    """终局复检对全文复跑：干净→空元组；含他人 PII→命中；owned 过滤同样生效。"""
    og = _make_guard(owned_values=("13812345678",))
    assert og.final_check("都是干净的内容。") == ()
    hits = og.final_check("张三手机13987654321，本人号13812345678")
    assert len(hits) == 1
    assert hits[0].kind == "pii"
    assert hits[0].rule == "phone_cn"


def test_excerpt_is_masked_and_capped() -> None:
    """D15 打码：摘录首尾各 2 字符 + 中间 *、≤40 字符——泄漏物原文不因审计二次落盘。"""
    og = _make_guard()
    og.feed("身份证号11010519900101123X。")
    assert og.hit is not None
    excerpt = og.hit.excerpt
    assert len(excerpt) <= 40
    assert excerpt.startswith("11")
    assert excerpt.endswith("3X")
    assert "*" in excerpt
    assert "0519900101" not in excerpt

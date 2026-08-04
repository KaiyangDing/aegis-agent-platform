"""M4.6 交付① lint：成本实验题库资产与缓存流量生成器（零真实调用，纯文件/纯函数）。

七条判据（沿 eval-lint 先例 tests/evals/test_seed_cases.py 的层次化样式）：
文件形状与 id 规则 / 申报分布精确成立 / 节内节间零重复 / 与评测集零交集（计划 §7 陷阱 3）/
工具题订单引用指向实验种子常量（importlib 复用 cost_common——I1 单一事实源）/
复述比例与「只从已流出前缀重抽」不变量 / 固定种子可精确重放。
实验本体（时序/费用敏感）不进 CI——00 §2.2 测试纪律。
"""

from __future__ import annotations

import importlib.util
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = ROOT / "evals" / "cost_questions.json"
EVAL_CASES_PATH = ROOT / "evals" / "cases.json"
_COMMON_SCRIPT = ROOT / "scripts" / "cost_common.py"

_KIND_BY_ID_LETTER = {"f": "faq", "r": "rag", "t": "tool", "c": "chitchat"}
_ID_RE = re.compile(r"^(cr|cc)-([frtc])(\d{2})$")
_ORDER_REF_RE = re.compile(r"EXP[RC]-\d{4}")
# 申报分布（P1 拍板 80 条 30/40/20/10；cache 唯一池 140 同配比）——报告口径节引用的
# 就是这两张表，测试钉死=报告里的「集合构成」不可能与文件漂移
_ROUTING_DIST = {"faq": 24, "rag": 32, "tool": 16, "chitchat": 8}
_CACHE_DIST = {"faq": 42, "rag": 56, "tool": 28, "chitchat": 14}
_READONLY_STATUSES = {"paid", "shipped", "delivered"}


@lru_cache(maxsize=1)
def _questions() -> dict[str, list[dict[str, str]]]:
    data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and set(data) == {"routing", "cache"}
    return data


@lru_cache(maxsize=1)
def _common() -> ModuleType:
    """importlib 装载共享底座脚本（M2.11 惯用法）：种子常量与生成器的单一事实源。"""
    spec = importlib.util.spec_from_file_location("cost_common_for_tests", _COMMON_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_file_shape_and_id_rules() -> None:
    """每行三键齐全；id 形如 cr-f01/cc-t28 且前缀-节、字母-kind 双向一致；id 全局唯一。"""
    seen_ids: set[str] = set()
    for section, id_prefix in (("routing", "cr"), ("cache", "cc")):
        for row in _questions()[section]:
            assert set(row) == {"id", "kind", "question"}, f"{row.get('id')} 键不齐"
            m = _ID_RE.match(row["id"])
            assert m is not None, f"id 形状非法：{row['id']}"
            assert m.group(1) == id_prefix, f"{row['id']} 落错节（应在 {section}）"
            assert _KIND_BY_ID_LETTER[m.group(2)] == row["kind"], f"{row['id']} 字母与 kind 不符"
            assert row["question"].strip() == row["question"] and row["question"], f"{row['id']} 题面空白"
            assert row["id"] not in seen_ids, f"id 重复：{row['id']}"
            seen_ids.add(row["id"])


def test_declared_distribution_exact() -> None:
    """申报分布精确成立：routing 24/32/16/8=80、cache 42/56/28/14=140——
    报告「集合构成」引用的数字与文件绝不漂移。"""
    routing = Counter(r["kind"] for r in _questions()["routing"])
    cache = Counter(r["kind"] for r in _questions()["cache"])
    assert dict(routing) == _ROUTING_DIST and sum(routing.values()) == 80
    assert dict(cache) == _CACHE_DIST and sum(cache.values()) == 140


def test_no_duplicates_within_or_across_sections() -> None:
    """全唯一是实验①口径的物质基础（00 §8.1：不受重复率污染）；
    节间零交集=两实验不混流（计划 §3 共同控制变量）。"""
    routing = [r["question"] for r in _questions()["routing"]]
    cache = [r["question"] for r in _questions()["cache"]]
    assert len(set(routing)) == len(routing), "routing 节内有重复题面"
    assert len(set(cache)) == len(cache), "cache 节内有重复题面"
    assert not set(routing) & set(cache), f"节间交集：{set(routing) & set(cache)}"


def test_zero_overlap_with_eval_cases() -> None:
    """与评测集字面零交集（04 M4：成本数字「没法被质疑是评测集凑出来的」；
    M4.5 §7 陷阱 2 同源纪律）。"""
    eval_questions = {c["question"] for c in json.loads(EVAL_CASES_PATH.read_text(encoding="utf-8"))}
    mine = {r["question"] for rows in _questions().values() for r in rows}
    assert not mine & eval_questions, f"与评测集撞题：{mine & eval_questions}"


def test_tool_questions_reference_experiment_seed_orders() -> None:
    """工具题订单引用指向实验种子（I1）：恰一个引用、前缀对节（EXPR↔routing、
    EXPC↔cache=账务不混流）、id 在种子清单内；非工具题零引用。
    连带钉种子常量本身：订单号全局唯一、状态只读集、归属=该实验驱动用户。"""
    common = _common()
    orders: dict[str, dict[str, object]] = {o["id"]: o for o in common.EXP_ORDERS}
    assert len(orders) == len(common.EXP_ORDERS), "实验订单号重复（mock_orders.id 全局主键）"
    for o in common.EXP_ORDERS:
        assert o["status"] in _READONLY_STATUSES, f"{o['id']} 状态越出只读面（P6）"
        expect_user = common.ROUTE_USER_ID if str(o["id"]).startswith("EXPR-") else common.CACHE_USER_ID
        assert o["user_id"] == expect_user, f"{o['id']} 归属用户不符"
    for section, prefix in (("routing", "EXPR-"), ("cache", "EXPC-")):
        for row in _questions()[section]:
            refs = _ORDER_REF_RE.findall(row["question"])
            if row["kind"] == "tool":
                assert len(refs) == 1, f"{row['id']} 工具题须恰一个订单引用，得到 {refs}"
                assert refs[0].startswith(prefix), f"{row['id']} 引用了另一实验的订单：{refs[0]}"
                assert refs[0] in orders, f"{row['id']} 引用未种订单：{refs[0]}"
            else:
                assert not refs, f"{row['id']} 非工具题不许引用订单：{refs}"


def test_replay_traffic_ratio_and_prefix_invariant() -> None:
    """生成器构造保证：140 池 @0.3 → 总长恰 200、复述恰 60（30% 精确成立）；
    首位恒唯一；每个复述在流内已出现过（只从前缀重抽）；唯一池全体出场。"""
    common = _common()
    pool = [r["question"] for r in _questions()["cache"]]
    traffic = common.build_cache_traffic(pool, replay_ratio=0.3, seed=42)
    assert len(traffic) == 200
    seen: set[str] = set()
    replays = 0
    for q in traffic:
        if q in seen:
            replays += 1  # 判据=「此前已流出」，与生成器槽位机制相互独立
        seen.add(q)
    assert replays == 60, f"复述条数 {replays} ≠ 60（30% 应精确成立）"
    assert seen == set(pool), "唯一池未全体出场（复述挤掉了 fresh 槽）"
    with pytest.raises(ValueError):
        common.build_cache_traffic(pool, replay_ratio=0.0)
    with pytest.raises(ValueError):
        common.build_cache_traffic([], replay_ratio=0.3)


def test_replay_traffic_seed_reproducible() -> None:
    """同 seed 逐条相等（流量可精确重放=报告可复算的前提）；异 seed 序列应不同。"""
    common = _common()
    pool = [r["question"] for r in _questions()["cache"]]
    a = common.build_cache_traffic(pool, seed=42)
    b = common.build_cache_traffic(pool, seed=42)
    assert a == b
    assert a != common.build_cache_traffic(pool, seed=43)

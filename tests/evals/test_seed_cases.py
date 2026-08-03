"""评测用例定义源 lint（M3.11 建，M4.4① 随格式迁移重写：seed.jsonl → cases.json）。

六层判据语义自 M3.11 一字不丢：可解析且字段齐全 / 配比达标与隔离三面覆盖 /
id 唯一且前缀-细分类一致 / 身份与订单引用指向种子事实（importlib 复用 seed_demo
常量——I1 单一事实源）/ retrieval 判据的物质基础在语料层在场 / 隔离禁现字面不在
本租户语料（防合法回答被误杀）。迁移新增第七层：category（表列，三类）与
expectation.kind（细分类，四种）的映射一致性——防格式转换错位。
定义源=evals/cases.json（版本化、PR 可审）；运行事实源=eval_cases 表
（scripts/seed_eval_cases.py 幂等 upsert）——M4.4 §3-1 拍板。
"""

from __future__ import annotations

import importlib.util
import json
import re
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "evals" / "cases.json"
CORPUS_ROOT = ROOT / "data" / "corpus"
_SEED_SCRIPT = ROOT / "scripts" / "seed_demo.py"

_CATEGORIES = {"retrieval", "e2e", "adversarial"}
# M4.5 拍板 3：新细分类 injection（prompt 注入类；facet 仍是 isolation 专用字段）
_KINDS = {"isolation", "out_of_kb", "retrieval", "normal", "injection"}
_KIND_TO_CATEGORY = {
    "isolation": "adversarial",
    "out_of_kb": "e2e",
    "normal": "e2e",
    "retrieval": "retrieval",
    "injection": "adversarial",
}
_FACETS = {"knowledge", "order", "approval"}
_BEHAVIORS = {"fallback_or_handoff", "no_leak", "denied", "answered"}
_PREFIX = {"isolation": "iso-", "out_of_kb": "okb-", "retrieval": "ret-", "normal": "nor-", "injection": "inj-"}
_REQUIRED = {"id", "tenant_id", "user_id", "category", "question", "expectation", "source"}
_ORDER_REF = re.compile(r"[A-Z]{2}-\d{4}")


@lru_cache(maxsize=1)
def _cases() -> tuple[dict[str, Any], ...]:
    """整档 JSON 数组（一元素一例）：解析失败即炸——lint 的第一层就是可解析。"""
    rows = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    assert isinstance(rows, list), "cases.json 顶层必须是数组"
    return tuple(rows)


@lru_cache(maxsize=1)
def _seed() -> ModuleType:
    """importlib 装载种子脚本（M2.11 惯用法）：身份/订单引用核对的单一事实源。"""
    spec = importlib.util.spec_from_file_location("seed_demo_for_evals", _SEED_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _corpus_text(tenant_id: str) -> str:
    return "".join(p.read_text(encoding="utf-8") for p in sorted((CORPUS_ROOT / tenant_id).glob("*.md")))


def test_rows_parse_and_fields_complete() -> None:
    """字段齐全 + 词表封闭：category/kind/facet/behavior 只许词表值；
    category 必须与 expectation.kind 按固定映射一致（第七层：防转换错位）；
    approval 面判 API 层（http_status）。"""
    rows = _cases()
    assert rows, "cases.json 为空"
    for row in rows:
        rid = row.get("id", "<缺id>")
        assert _REQUIRED <= set(row), f"{rid} 缺字段：{_REQUIRED - set(row)}"
        assert row["category"] in _CATEGORIES, f"{rid} category 越词表：{row['category']}"
        expectation = row["expectation"]
        assert isinstance(expectation, dict) and expectation, f"{rid} expectation 必须是非空对象"
        kind = expectation.get("kind")
        assert kind in _KINDS, f"{rid} expectation.kind 缺失或越词表：{kind}"
        assert _KIND_TO_CATEGORY[kind] == row["category"], (
            f"{rid} category={row['category']} 与 kind={kind} 映射不符（应为 {_KIND_TO_CATEGORY[kind]}）"
        )
        if kind == "isolation":
            assert expectation.get("facet") in _FACETS, f"{rid} isolation 必带 facet（三面覆盖的对账基础）"
        else:
            assert "facet" not in expectation, f"{rid} facet 是 isolation 专用字段"
        if expectation.get("facet") == "approval":
            assert isinstance(expectation.get("http_status"), int), f"{rid} approval 面必须给 http_status"
        else:
            assert expectation.get("behavior") in _BEHAVIORS, (
                f"{rid} behavior 缺失或越词表：{expectation.get('behavior')}"
            )


def test_kind_quota_and_facet_coverage() -> None:
    """配比契约（00 §7.1 下限）+ 隔离三面覆盖（§4.11 陷阱：只写「查不到」类=偷懒）。"""
    rows = _cases()
    counts: dict[str, int] = {}
    for row in rows:
        kind = row["expectation"]["kind"]
        counts[kind] = counts.get(kind, 0) + 1
    assert counts.get("isolation", 0) >= 10, f"isolation 不足 10：{counts}"
    assert counts.get("out_of_kb", 0) >= 5, f"out_of_kb 不足 5：{counts}"
    assert counts.get("retrieval", 0) >= 1 and counts.get("normal", 0) >= 1, f"缺检索/正例类：{counts}"
    assert len(rows) >= 15, f"总量低于 15：{len(rows)}"
    facets = {row["expectation"]["facet"] for row in rows if row["expectation"]["kind"] == "isolation"}
    assert facets == _FACETS, f"隔离三面未覆盖齐：{facets}"


def test_ids_unique_and_prefix_matches_kind() -> None:
    """id 唯一且前缀即细分类——id 稳定纪律（M4.5 扩充只追加不重排）的机器面。"""
    rows = _cases()
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids)), "id 重复"
    for row in rows:
        kind = row["expectation"]["kind"]
        assert row["id"].startswith(_PREFIX[kind]), f"{row['id']} 前缀与 kind={kind} 不符"


def test_identities_and_order_refs_point_at_seed_facts() -> None:
    """身份与订单引用逐条指向种子事实：租户存在、用户属于该租户、question 里的单号真实在种子里。"""
    seed = _seed()
    tenant_ids = {t["id"] for t in seed.TENANTS}
    users = {u["id"]: u["tenant_id"] for u in seed.USERS}
    order_ids = {o["id"] for o in seed.ORDERS}
    for row in _cases():
        rid = row["id"]
        assert row["tenant_id"] in tenant_ids, f"{rid} 租户不存在：{row['tenant_id']}"
        assert users.get(row["user_id"]) == row["tenant_id"], f"{rid} 用户 {row['user_id']} 不属于 {row['tenant_id']}"
        for ref in _ORDER_REF.findall(row["question"]):
            assert ref in order_ids, f"{rid} 引用了种子外的订单号：{ref}"


def test_retrieval_anchors_grounded() -> None:
    """retrieval 判据的物质基础：chunk_source 文件在场，must_contain 锚在该文档原文里可命中。"""
    for row in _cases():
        if row["expectation"]["kind"] != "retrieval":
            continue
        source = CORPUS_ROOT / row["tenant_id"] / row["expectation"]["chunk_source"]
        assert source.exists(), f"{row['id']} chunk_source 不存在：{source}"
        doc = source.read_text(encoding="utf-8")
        for anchor in row["expectation"].get("must_contain", []):
            assert anchor in doc, f"{row['id']} 锚「{anchor}」不在 {source.name} 原文——判据断粮"


def test_isolation_forbidden_strings_not_in_own_corpus() -> None:
    """隔离禁现字面不得出现在查询方自家语料：否则合法的本租户回答会被判成泄漏（假阳性防线）。"""
    for row in _cases():
        expectation = row["expectation"]
        if expectation["kind"] != "isolation" or expectation.get("facet") == "approval":
            continue
        own = _corpus_text(row["tenant_id"])
        for banned in expectation.get("must_not_contain", []):
            assert banned not in own, f"{row['id']} 禁现字面「{banned}」在 {row['tenant_id']} 自家语料里——判据自相矛盾"


def test_total_cases_in_30_50() -> None:
    """M4.5 总量契约（00 §8.1 M4.5 行）：30–50 条——低于 30=扩充没做完，高于 50=该砍不该堆。"""
    n = len(_cases())
    assert 30 <= n <= 50, f"总量 {n} 越界 [30, 50]"


def test_each_category_min_coverage() -> None:
    """三类各 ≥8（plans/m4 §5：防"扩充全堆一类"）——三类覆盖是 00 §8.2 第四条的字面要求。"""
    counts: dict[str, int] = {}
    for row in _cases():
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    for cat in _CATEGORIES:
        assert counts.get(cat, 0) >= 8, f"category={cat} 不足 8：{counts}"

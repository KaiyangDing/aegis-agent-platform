"""M3.11 交付②：种子评测集文件 lint（evals/cases/seed.jsonl——落表归 M4.4，§7 陷阱 11 勿越步建表）。

六层判据：可解析且字段齐全 / 配比达标与隔离三面覆盖 / id 唯一且前缀-类别一致 /
身份与订单引用指向种子事实（importlib 复用 seed_demo 常量——I1 单一事实源）/
retrieval 判据的物质基础在语料层在场 / 隔离禁现字面不在本租户语料（防合法回答被误杀）。
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
CASES_PATH = ROOT / "evals" / "cases" / "seed.jsonl"
CORPUS_ROOT = ROOT / "data" / "corpus"
_SEED_SCRIPT = ROOT / "scripts" / "seed_demo.py"

_KINDS = {"isolation", "out_of_kb", "retrieval", "normal"}
_FACETS = {"knowledge", "order", "approval"}
_BEHAVIORS = {"fallback_or_handoff", "no_leak", "denied", "answered"}
_PREFIX = {"isolation": "iso-", "out_of_kb": "okb-", "retrieval": "ret-", "normal": "nor-"}
_REQUIRED = {"id", "kind", "tenant_id", "user_id", "query", "expect", "note"}
_ORDER_REF = re.compile(r"[A-Z]{2}-\d{4}")


@lru_cache(maxsize=1)
def _cases() -> tuple[dict[str, Any], ...]:
    """逐行 json.loads（一行一例）：解析失败带行号炸——lint 的第一层就是可解析。"""
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(CASES_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:  # pragma: no cover - 失败路径即诊断信息
            raise AssertionError(f"seed.jsonl 第 {lineno} 行不是合法 JSON：{exc}") from exc
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
    """字段齐全 + 词表封闭：kind/facet/behavior 只许词表值；approval 面判 API 层（http_status）。"""
    rows = _cases()
    assert rows, "seed.jsonl 为空"
    for row in rows:
        rid = row.get("id", "<缺id>")
        assert _REQUIRED <= set(row), f"{rid} 缺字段：{_REQUIRED - set(row)}"
        assert row["kind"] in _KINDS, f"{rid} kind 越词表：{row['kind']}"
        expect = row["expect"]
        assert isinstance(expect, dict) and expect, f"{rid} expect 必须是非空对象"
        if row["kind"] == "isolation":
            assert row.get("facet") in _FACETS, f"{rid} isolation 必带 facet（三面覆盖的对账基础）"
        else:
            assert "facet" not in row, f"{rid} facet 是 isolation 专用字段"
        if row.get("facet") == "approval":
            assert isinstance(expect.get("http_status"), int), f"{rid} approval 面必须给 http_status"
        else:
            assert expect.get("behavior") in _BEHAVIORS, f"{rid} behavior 缺失或越词表：{expect.get('behavior')}"


def test_kind_quota_and_facet_coverage() -> None:
    """配比契约（00 §7.1 下限）+ 隔离三面覆盖（§4.11 陷阱：只写「查不到」类=偷懒）。"""
    rows = _cases()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    assert counts.get("isolation", 0) >= 10, f"isolation 不足 10：{counts}"
    assert counts.get("out_of_kb", 0) >= 5, f"out_of_kb 不足 5：{counts}"
    assert counts.get("retrieval", 0) >= 1 and counts.get("normal", 0) >= 1, f"缺检索/正例类：{counts}"
    assert len(rows) >= 15, f"总量低于 15：{len(rows)}"
    facets = {row["facet"] for row in rows if row["kind"] == "isolation"}
    assert facets == _FACETS, f"隔离三面未覆盖齐：{facets}"


def test_ids_unique_and_prefix_matches_kind() -> None:
    """id 唯一且前缀即类别——id 稳定纪律（M4.5 扩充只追加不重排）的机器面。"""
    rows = _cases()
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids)), "id 重复"
    for row in rows:
        assert row["id"].startswith(_PREFIX[row["kind"]]), f"{row['id']} 前缀与 kind={row['kind']} 不符"


def test_identities_and_order_refs_point_at_seed_facts() -> None:
    """身份与订单引用逐条指向种子事实：租户存在、用户属于该租户、query 里的单号真实在种子里。"""
    seed = _seed()
    tenant_ids = {t["id"] for t in seed.TENANTS}
    users = {u["id"]: u["tenant_id"] for u in seed.USERS}
    order_ids = {o["id"] for o in seed.ORDERS}
    for row in _cases():
        rid = row["id"]
        assert row["tenant_id"] in tenant_ids, f"{rid} 租户不存在：{row['tenant_id']}"
        assert users.get(row["user_id"]) == row["tenant_id"], f"{rid} 用户 {row['user_id']} 不属于 {row['tenant_id']}"
        for ref in _ORDER_REF.findall(row["query"]):
            assert ref in order_ids, f"{rid} 引用了种子外的订单号：{ref}"


def test_retrieval_anchors_grounded() -> None:
    """retrieval 判据的物质基础：chunk_source 文件在场，must_contain 锚在该文档原文里可命中。"""
    for row in _cases():
        if row["kind"] != "retrieval":
            continue
        source = CORPUS_ROOT / row["tenant_id"] / row["expect"]["chunk_source"]
        assert source.exists(), f"{row['id']} chunk_source 不存在：{source}"
        doc = source.read_text(encoding="utf-8")
        for anchor in row["expect"].get("must_contain", []):
            assert anchor in doc, f"{row['id']} 锚「{anchor}」不在 {source.name} 原文——判据断粮"


def test_isolation_forbidden_strings_not_in_own_corpus() -> None:
    """隔离禁现字面不得出现在查询方自家语料：否则合法的本租户回答会被判成泄漏（假阳性防线）。"""
    for row in _cases():
        if row["kind"] != "isolation" or row.get("facet") == "approval":
            continue
        own = _corpus_text(row["tenant_id"])
        for banned in row["expect"].get("must_not_contain", []):
            assert banned not in own, f"{row['id']} 禁现字面「{banned}」在 {row['tenant_id']} 自家语料里——判据自相矛盾"

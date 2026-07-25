"""轻量重排纯函数（M3.5 交付①，plans/m3-detailed §4.5 / 00 §7.1 M3.5 行）。

重排是模块边界（00 §10.3）：cross-encoder 属 v2，替换发生在本文件内、不动调用方。
v1 规则 = 相似度与关键词覆盖的加权和：向量召回擅长语义近邻，但对"R68 Pro"这类
字面锚点（型号/单号/专名）会偏爱同族近义词——覆盖率把字面命中拉回来
（M2.11 录制实录同源教训：纯 CJK 专名劣于字母数字串）。

确定性口径：sorted 稳定排序、同分保输入序（与 context._pack_snippets 同款）；
零分词依赖——CJK 二元组 + 字母数字段，与 core/tokens.py 同一把尺哲学（C25）。
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

# 权重定成模块常量不进 Settings：这是检索质量参数不是运维参数，调它=改算法
# 要走实测校准（交付④），不该被环境变量随手拧
_SIMILARITY_WEIGHT = 0.7
_COVERAGE_WEIGHT = 0.3

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")  # 范围镜像 tokens.py:15——同一把尺
_WORD_RE = re.compile(r"[0-9A-Za-z]+")  # 非 CJK 单元：字母数字段（型号/单号天然成段）


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """检索命中单元（chunks 行的查询时视图，交付② SQL 取回后构造）。

    定义在 rerank 侧而非 retrieve 侧：调用方向 retrieve→rerank 单向，
    共享类型住依赖下游——分层代价，与 core 不向上 import runtime 同款。
    """

    chunk_id: int
    document_id: str
    text: str
    similarity: float  # 1 - 余弦距离（<=> 返回的是距离，0=同向——§4.5 陷阱第 3 条）
    score: float = 0.0  # 重排后综合分，rerank() 回填；SQL 取回时置默认
    meta: Mapping[str, Any] = field(default_factory=dict)


def _query_units(query: str) -> frozenset[str]:
    """查询 → 匹配单元集合：CJK 连续段取相邻二元组（孤字自成单元，否则单字
    查询永远零单元）、非 CJK 取字母数字段小写归一。集合语义=重复词不重复计权。"""
    units: set[str] = set()
    for run in _CJK_RE.findall(query):
        if len(run) == 1:
            units.add(run)
        else:
            units.update(run[i : i + 2] for i in range(len(run) - 1))
    units.update(w.lower() for w in _WORD_RE.findall(query))
    return frozenset(units)


def keyword_coverage(query: str, text: str) -> float:
    """query 匹配单元在 text 中的命中率 ∈ [0,1]；query 无单元（空/纯标点）返回 0.0。

    命中判据 = 小写化子串包含："R680 含 R68"一类过匹配显式接受——这是 0.3 权重
    的辅助信号，宁粗勿引分词器（CJK 二元组对小写化不敏感，一次 lower 两族通用）。
    """
    units = _query_units(query)
    if not units:
        return 0.0
    lowered = text.lower()
    return sum(1 for u in units if u in lowered) / len(units)


def rerank(query: str, hits: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
    """按综合分降序返回新列表：score = 0.7×similarity + 0.3×keyword_coverage。

    不截断（top_k 归 Retriever.search）、不过滤（阈值兜底同归 search）——本函数
    只管"重新打分+排序"一件事。meta 规则位挂点：需要业务加成时（如
    meta["priority"] 置顶）在 score 表达式后追加一项，改动收在本文件不散落调用方。
    """
    rescored = [
        replace(h, score=_SIMILARITY_WEIGHT * h.similarity + _COVERAGE_WEIGHT * keyword_coverage(query, h.text))
        for h in hits
    ]
    return sorted(rescored, key=lambda h: -h.score)  # sorted 稳定：同分保输入序（确定性）

"""token 估算：护栏用估算，账单用实测（00 §2.2 口径，评审 C25 裁决）。

预算闸门与上下文预算需要在调用前知道"大概多少"，而"精确"是伪命题：
Qwen 与 DeepSeek 词表不同，fallback 换模型后同一段文本没有唯一 token 数。
启发式：CJK ≈ 1 token/字，其余 ≈ 4 字符/token；预算数字自带 ±15% 余量消化误差。
真实计费永远以供应商返回的 usage 回填 usage_ledger 为准（M1.11）。
M2.5 ContextBuilder 的六层预算复用本估算器——L1/L2 同一把尺。
"""

CJK_FIRST = "一"
CJK_LAST = "鿿"
CJK_RANGE = f"{CJK_FIRST}-{CJK_LAST}"
"""CJK 判定区间单点（M4.7 ⑳）：估算器（本文件）/切块兜底（rag/ingest._hard_split）/
重排分词（rag/rerank._CJK_RE）三处同一把尺——此前各自内联、"镜像"关系只靠注释维系，
改区间漏一处=预算与检索的字尺静默分家。逐字符比较用 CJK_FIRST/CJK_LAST，
正则字符类内嵌 CJK_RANGE。"""


def estimate_tokens(text: str) -> int:
    """纯启发式，零分词依赖（tiktoken 是 OpenAI 词表，对 Qwen 中文系统性偏差）。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if CJK_FIRST <= ch <= CJK_LAST)
    other = len(text) - cjk
    return cjk + (other + 3) // 4

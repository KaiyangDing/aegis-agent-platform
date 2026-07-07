"""token 估算：护栏用估算，账单用实测（00 §2.2 口径，评审 C25 裁决）。

预算闸门与上下文预算需要在调用前知道"大概多少"，而"精确"是伪命题：
Qwen 与 DeepSeek 词表不同，fallback 换模型后同一段文本没有唯一 token 数。
启发式：CJK ≈ 1 token/字，其余 ≈ 4 字符/token；预算数字自带 ±15% 余量消化误差。
真实计费永远以供应商返回的 usage 回填 usage_ledger 为准（M1.11）。
M2.5 ContextBuilder 的六层预算复用本估算器——L1/L2 同一把尺。
"""


def estimate_tokens(text: str) -> int:
    """纯启发式，零分词依赖（tiktoken 是 OpenAI 词表，对 Qwen 中文系统性偏差）。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return cjk + (other + 3) // 4

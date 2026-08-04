"""切块纯函数与摄取任务的 wire 契约（M3.4 交付③，plans/m3-detailed §4.4 / 14d 决策 A）。

INGEST_TASK_NAME 落本模块的原因（决策 A）：层契约 `api | workers` 互不 import，
任务名是两端共享的 wire 契约——apps 是双方共同的下层，唯一同源点
（workers 侧 @task(name=...) 注册、api 侧 send_task 点名，一致性由测试钉死）。
split_text 是纯函数：无 IO 无状态，参数即策略——切块策略对召回的影响是
00 §7.2 点名的面试考点，取舍全部写在 docstring。
"""

from aegis.core.tokens import CJK_FIRST, CJK_LAST, estimate_tokens

INGEST_TASK_NAME = "aegis.ingest_document"
"""Celery 任务名（wire 契约）：改名=断掉 api→worker 的投递，两端必须同步——
tests/workers/test_ingest_resume.py 的注册断言在 CI 钉住它。"""

_SENTENCE_ENDS = "。！？!?.\n"
"""句界字符集（朴素规则不引 NLP 依赖——与 guardrails 切句同族）。
已知噪音：ascii 小数点会误切（"3.14"）——语料以中文 md/txt 为主，接受。"""


def split_text(text: str, *, target_tokens: int = 400, overlap_tokens: int = 50) -> list[str]:
    """按段落聚合到 token 预算的切块器（estimate_tokens 做尺——C25 护栏用估算）。

    三级降级的语义完整性承诺：段落 → 句子 → 硬切窗。
    - 段落（空行分隔）是第一承诺：聚合到预算即封块，绝不腰斩段落；
    - 单段超预算：退一级按句界切（_SENTENCE_ENDS），单句仍超再退硬切窗；
    - target_tokens=400：太小→语义碎片化、召回后拼不回上下文；太大→单块噪音
      稀释检索精度、且吃 ContextBuilder 的 retrieval 预算（六层编译的下游）；
    - overlap_tokens=50：块间重叠对抗"答案跨块边界"，代价是索引行数膨胀；
      种子=前块尾部完整段落（总额 ≤ overlap），装不下宁缺毋滥（0 种子合法）；
    - 估算是启发式（±15% 口径自带余量）：CJK 恰 1 token/字——预算敏感的测试用 CJK 语料；
      已知余量内噪音：段间连接符成本未逐段入账（k 段 ≈ (k-1)/2 token）、混排硬切窗 ±1。
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf: list[str] = []  # 当前块的段落列表（可能带上一块的 overlap 种子）
    buf_cost = 0
    fresh = 0  # 上次封块后新加入的段落数——纯种子不算一块（防尾部吐出重复残块）

    def flush() -> None:
        nonlocal buf, buf_cost, fresh
        chunks.append("\n\n".join(buf))
        seed: list[str] = []
        cost = 0
        for para in reversed(buf):  # 从尾往前收种子：保住与下块最相邻的上下文
            pt = estimate_tokens(para)
            if cost + pt > overlap_tokens:
                break
            seed.insert(0, para)
            cost += pt
        buf, buf_cost, fresh = seed, cost, 0

    for para in paragraphs:
        pt = estimate_tokens(para)
        if pt > target_tokens:
            if fresh:
                flush()
            chunks.extend(_split_long_paragraph(para, target_tokens))
            buf, buf_cost, fresh = [], 0, 0  # 超长段独立成块，不携带种子（语义单元已自立）
            continue
        if fresh and buf_cost + pt > target_tokens:
            flush()
        if not fresh and buf and buf_cost + pt > target_tokens:
            # 两处入口共用的种子体检（含刚 flush 完的同轮）：种子+新段装不下就丢种子——
            # 绝不产出超预算块（宁丢重叠不破预算；③校验反例：30+380/400/50）
            buf, buf_cost = [], 0
        buf.append(para)
        buf_cost += pt
        fresh += 1
    if fresh:
        chunks.append("\n\n".join(buf))
    return chunks


def _split_long_paragraph(para: str, target_tokens: int) -> list[str]:
    """超预算段落的二级切分：句子聚合到预算；单句仍超 → 硬切窗。"""
    pieces: list[str] = []
    buf: list[str] = []
    buf_cost = 0
    for sent in _split_sentences(para):
        st = estimate_tokens(sent)
        if st > target_tokens:
            if buf:
                pieces.append("".join(buf))
                buf, buf_cost = [], 0
            pieces.extend(_hard_split(sent, target_tokens))
            continue
        if buf and buf_cost + st > target_tokens:
            pieces.append("".join(buf))
            buf, buf_cost = [], 0
        buf.append(sent)
        buf_cost += st
    if buf:
        pieces.append("".join(buf))
    return pieces


def _split_sentences(para: str) -> list[str]:
    buf: list[str] = []
    out: list[str] = []
    for ch in para:
        buf.append(ch)
        if ch in _SENTENCE_ENDS:
            sent = "".join(buf).strip()
            if sent:
                out.append(sent)
            buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _hard_split(sent: str, target_tokens: int) -> list[str]:
    """三级兜底：按每字符估算成本累计到预算即切（CJK=1、其余 0.25——与
    estimate_tokens 同一 CJK 区间与比率，tokens.py:15-17 的逐字符形态）。"""
    parts: list[str] = []
    buf: list[str] = []
    cost = 0.0
    for ch in sent:
        buf.append(ch)
        cost += 1.0 if CJK_FIRST <= ch <= CJK_LAST else 0.25
        if cost >= target_tokens:
            parts.append("".join(buf))
            buf, cost = [], 0.0
    if buf:
        parts.append("".join(buf))
    return parts

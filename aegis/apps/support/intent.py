"""意图路由（M3.6，02 §2⑤ / ADR-002 决策 2）：fast 档单次分类——不是 Agent。

无循环、无工具、绝不重试（一次调用是 ADR-002 红线）；分诊失败一律
Intent.AGENT 直走主 Agent 标准档（C34 fail-open，plans/m3 D8）。
分支接线（FAQ 直答轮写事件 D7 / 主 Agent 启动 / handoff 直通）归 chat
服务层（M3.8/M3.10 汇合处）；本模块只提供 classify 与 answer_faq 两个
机制函数，对"分到哪一路之后发生什么"一无所知。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from enum import StrEnum

from aegis.apps.support.prompts import FAQ_DIRECT_RULES
from aegis.gateway.schema import LLMRequest, Message, TextDelta
from aegis.runtime.runtime import GatewayLike

logger = logging.getLogger(__name__)


class Intent(StrEnum):
    """四路分诊 + fail-open 落点。前四值 = 分类 prompt 词表的字面词。"""

    FAQ = "faq"  # 直答：单次调用即回，旅程结束（含精确缓存命中路径）
    RAG = "rag"  # 知识型：主 Agent（M3.8 预热检索注入首轮）
    TOOL = "tool"  # 业务操作型：主 Agent（工具）
    HANDOFF = "handoff"  # 点名人工/投诉升级：直接转人工（M3.8 create_handoff）
    AGENT = "agent"  # 分诊失败落点（C34/D8）：主 Agent 标准档——刻意不在 prompt 词表内


INTENT_PROMPT = (
    "你是客服系统的意图分类器。把用户消息归入以下四类之一，"
    "只输出对应的英文单词，不要输出任何解释、标点或其他内容。\n"
    "faq：问候、致谢，或平台通用信息（营业时间、联系方式、平台使用方法）——"
    "仅当消息不依赖上文即可完整理解；\n"
    "rag：需要查知识库的政策与商品知识问题（退货政策、保修规则、配送范围）；\n"
    "tool：需要查询或操作用户个人业务数据（订单、物流、退款、工单、优惠券）；\n"
    "handoff：用户明确要求转人工，或投诉升级、强烈不满。\n"
    "省略主语或指代上文的跟进追问（如「一般要多久？」）不判 faq，按内容归 rag 或 tool。"
)
"""分类指令。参与 M3.11 cassette 录制语义——改动会让重录 diff 扩散，
定了不动（与 guardrails._CLASSIFY_PROMPT / runtime._SUMMARIZE_PROMPT 同款纪律）。"""


_INTENT_WORDS = (Intent.FAQ, Intent.RAG, Intent.TOOL, Intent.HANDOFF)
"""解析白名单 = prompt 词表四词；AGENT 是失败落点不是模型词汇，刻意不在其中。"""


def _parse_intent(raw: str) -> Intent:
    """宽容解析（plans §4.6 陷阱 1）：恰含词表一词才算数。

    strip+lower 后做子串扫描——模型加料（"分类：faq"/"faq。"）仍可救回；
    零个或多个命中（如 "faq或rag"）都是不可靠输出 → AGENT。
    宽容只用于救格式，绝不把歧义洗成裁决（与 build_classifier 的
    严格白名单同一哲学，只是失败落点不同：那边 ValueError、这边 AGENT）。
    """
    answer = raw.strip().lower()
    hits = [word for word in _INTENT_WORDS if word.value in answer]
    if len(hits) == 1:
        return hits[0]
    # M4.2③（观察 ㉓)：三条通往 AGENT 的路此前只有网关异常留痕——零/多词这条补上，
    # "分诊失败率"才可观测。只记命中数与长度：模型原文可能复述用户消息（打码纪律）
    logger.warning("意图解析不可靠，fail-open 走主 Agent：hits=%d len=%d", len(hits), len(answer))
    return Intent.AGENT


async def classify(
    gateway: GatewayLike,
    text: str,
    *,
    tenant_id: str,
    session_id: str,
    deadline_s: float = 10.0,
) -> Intent:
    """一次 fast 档分类调用：消费流拼文本 → 白名单解析；失败一律 AGENT。

    fail-open 捕获面是 except Exception（与 check_input/RetrievalProvider
    两处 C34 样板一致）：分诊是增强层，网关六类也好解析 bug 也好，都不该
    杀掉用户请求；留痕不记用户原文（打码纪律）。
    deadline 走 LLMRequest.deadline_s 传播，不包 asyncio.timeout（C1）。
    """
    request = LLMRequest(
        tier="fast",  # 02 §4 档位语义：意图分类是 fast 档的名分场景
        messages=[
            Message(role="system", content=INTENT_PROMPT),
            Message(role="user", content=text),
        ],
        tenant_id=tenant_id,
        session_id=session_id,  # 回放匹配键第一段（C10）——组装方必带
        deadline_s=deadline_s,
    )
    parts: list[str] = []
    try:
        stream = gateway.complete(request)  # def：调用即得 async 生成器，不 await
        async with aclosing(stream):
            async for chunk in stream:
                if isinstance(chunk, TextDelta):
                    parts.append(chunk.text)
    except Exception as e:  # C34 fail-open：分诊挂 → 主 Agent 标准档（D8）
        logger.warning(
            "意图分类失败，fail-open 走主 Agent：session=%s error=%s: %s",
            session_id,
            type(e).__name__,
            e,
        )
        return Intent.AGENT
    return _parse_intent("".join(parts))


async def answer_faq(
    gateway: GatewayLike,
    question: str,
    *,
    tenant_id: str,
    session_id: str,
    faq_digest: str,
    deadline_s: float = 10.0,
) -> AsyncIterator[str]:
    """FAQ 直答：单次 fast 档调用流式产出文本（02 §2⑤：此路旅程结束，不启动循环）。

    system=faq_digest+平台禁编造规则行（M4.4③ ㉖：digest 政策归租户配置，
    禁编造是平台底线——SYSTEM_PROMPT 规则 3 的直答版，注入归 M3.8 装配、
    文案归 M3.11 种子；本函数机制不定政策，但底线不归租户）。
    """
    request = LLMRequest(
        tier="fast",
        messages=[
            Message(role="system", content=faq_digest + FAQ_DIRECT_RULES),
            Message(role="user", content=question),
        ],
        tenant_id=tenant_id,
        session_id=session_id,
        deadline_s=deadline_s,
    )
    stream = gateway.complete(request)
    async with aclosing(stream):
        async for chunk in stream:
            if isinstance(chunk, TextDelta):
                yield chunk.text

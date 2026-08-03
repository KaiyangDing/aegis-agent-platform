"""展示层 PII 打码单点（M4.1 交付①，02 §7.3）。

events 表存原文是恢复事实源（02 §3）——脱敏绝不发生在写路径，只发生在
展示出口：trace API、日志导出同用本模块，全仓打码只有这一个入口。
模式事实源与运行时出口守卫共用同一张表（guardrails.PII_RULES_V1，M2.8）：
一张表两个消费面（流式拦截 / 展示打码），不复制常量，规则演进两面自动同步。
不变量：本模块绝不抛异常——展示层故障不许拖垮查询（与"缓存计量故障
绝不拖垮请求"同向，00 §2.2）；失败整段替换为掩码占位，宁可多遮不漏。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aegis.runtime.guardrails import PII_RULES_V1

MASK_ERROR_TEXT = "<mask_error>"
"""mask_text 内部故障时的整段占位——消费方与测试都认这个字面量。"""

_MASK_ERROR_PAYLOAD: dict[str, Any] = {"mask_error": True}
"""mask_payload 故障占位：保持 dict 形状（TraceEvent.payload 契约），整段顶替。"""


def mask_text(text: str) -> str:
    """逐规则打码：命中替换为 ***{规则名}***（规则名即审计词汇）。

    规则间无顺序依赖：PII_RULES_V1 各模式自带数字边界断言，
    18 位证号不会被 11 位手机规则腰斩——不靠"长模式在前"的排序纪律。
    """
    try:
        masked = text
        for rule in PII_RULES_V1:
            masked = rule.pattern.sub(f"***{rule.name}***", masked)
        return masked
    except Exception:  # 防御底线：诡异输入宁可整段遮掉，绝不把异常抛给查询
        return MASK_ERROR_TEXT


def _mask_value(value: Any) -> Any:
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, Mapping):
        return {key: _mask_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_value(item) for item in value]
    return value  # 数字/布尔/None 等非文本标量：结构事实，原样


def mask_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """递归遍历事件 payload：只处理 str 叶子，键与非字符串标量原样。

    返回新 dict，绝不就地改写入参——上游持有的是 ORM 行 payload 的引用，
    就地改等于污染事实源在内存里的镜像。
    """
    try:
        return {key: _mask_value(item) for key, item in payload.items()}
    except Exception:  # 同 mask_text：结构性防御，占位保持 dict 形状
        return dict(_MASK_ERROR_PAYLOAD)

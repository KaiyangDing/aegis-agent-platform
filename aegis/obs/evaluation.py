"""评测双表（M4.4①，00 §8.1 M4.4 行）：eval_cases 用例登记 / eval_runs 每用例每批次一行。

定义源在 repo（evals/cases.json）、运行事实源在表（§3-1 拍板）：表是 runner 的唯一
读面，趋势按 case_id 串联（id 稳定不重排纪律的存储侧意义）。建表口径全库一致
（A.8）：应用侧 String(64) id、无 FK、枚举存字符串列+代码层 StrEnum、created_at 用
DB 钟、钱走 Numeric/Decimal（金额不过 float）。eval_cases 带 tenant_id 列 → RLS
名单第十表（迁移自带 ENABLE+策略，M3.3 前置义务）；eval_runs 无 tenant_id
（批次是平台活动，按 batch_id/case_id 检索——events 先例）。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis.core.db import Base


class EvalCategory(StrEnum):
    """三类用例（04 M4）：检索质量（机器判）/ 端到端（judge 1–5 分）/ 对抗（机器硬断言优先）。"""

    RETRIEVAL = "retrieval"
    E2E = "e2e"
    ADVERSARIAL = "adversarial"


class EvalVerdict(StrEnum):
    """三态判定：error=执行/judge 异常，不算 fail——异常不许伪装成质量信号。"""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


class EvalCaseRecord(Base):
    """用例行：expectation 按 category 结构化（判据键词表见 evals/README §3 与 docs/eval-rubrics.md）。"""

    __tablename__ = "eval_cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 形如 iso-01；稳定不重排
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)  # 执行身份：用例绑定演示租户
    user_id: Mapped[str] = mapped_column(String(64))  # 会话行需要完整身份（P2：run 前建行）
    category: Mapped[str] = mapped_column(String(16), index=True)
    question: Mapped[str] = mapped_column(Text)
    expectation: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(16), default="seed")  # seed | m4.5
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)  # 运营开关：临时收窄控费批次
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalRunRecord(Base):
    """结果行：每用例每批次一行；批次聚合 GROUP BY batch_id 得出（02 §3 只列两表，不加第三张）。"""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True)  # 无 FK（P4），应用层引用
    verdict: Mapped[str] = mapped_column(String(16))
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # e2e 1–5；其余 None
    judge_model: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # 回显名（C36：strong 链含 fallback，中途换模必须留痕）
    answer_digest: Mapped[str | None] = mapped_column(Text, nullable=True)  # 被评回答摘要（诊断域，非断言面）
    judge_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)  # 本用例总消耗（被评+judge）
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_eval_runs_case_created", "case_id", "created_at"),)  # 趋势查询路径

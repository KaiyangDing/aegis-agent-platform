"""知识库摄取两表 ORM（M3.4 交付①，plans/m3-detailed §4.4 / P6 拍板 / ADR-006）。

拆表口径（P6）：文档级事实（source/status/error/chunk_count）归 documents，
块级事实（text/embedding/embedding_model）归 chunks。
- chunks.tenant_id 是刻意冗余：检索 WHERE 与 RLS 策略都直接吃它——
  隔离是硬防线，不为省一列引入 JOIN（ADR-006"越权隔离"层）；
- embedding 可空 = 断点续传的实现基座：切块先落文本（NULL），回填循环按
  IS NULL 谓词捞活，一批失败重试天然跳过已回填行（§4.4 步骤 3）；
- UNIQUE(document_id, seq)：切块重试/并发重复投递的幂等锚，数据库兜底；
- 不带 FK（P4 同款口径）：表间引用靠应用层，隔离靠 WHERE+RLS 不靠参照完整性。
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aegis.core.db import Base

EMBEDDING_DIMS = 1024
"""text-embedding-v4 显式指定的输出维度（ADR-006）：vector(1024) 列、
EmbeddingClient(dimensions=1024)（交付②）与本常量同一事实源。
换模型/换维度 = ADR-006 的灰度迁移运维动作（双列并存切读），不是改这个数。"""


class IngestStatus(StrEnum):
    """documents.status 合法值——String 列 + 代码守护（与 Role/RunState 同口径：
    加值改代码，不跑 ALTER TYPE）。"""

    PENDING = "pending"  # API 已落单、任务未开工（202 返回体里的初始态）
    PROCESSING = "processing"  # 任务进行中；重试期间保持不回摆（状态是进度不是心跳）
    DONE = "done"  # 全部 chunk 已回填向量（终态）
    FAILED = "failed"  # Celery max_retries 耗尽的终局（终态，error 列存死因）


class DocumentRecord(Base):
    """documents：一次上传一行；status 由摄取任务推进（PENDING→PROCESSING→DONE/FAILED）。"""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 应用侧 uuid4().hex（API 落单时生成）
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)  # RLS 策略列
    source: Mapped[str] = mapped_column(String(256))  # 文件名/来源标识（v1 纯文本上传）
    status: Mapped[str] = mapped_column(String(16))  # IngestStatus.value
    error: Mapped[str | None] = mapped_column(Text, nullable=True)  # FAILED 时的死因文本
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)  # DONE 时回填；ORM 默认（裸 INSERT 不享受）
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB)  # 平台不解释（与 tenants.config 同哲学）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChunkRecord(Base):
    """chunks：一块一行；embedding NULL=待回填（续传谓词），非 NULL 时 embedding_model 同步在场。"""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)  # 无 FK（P4），应用层引用
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)  # 冗余列：WHERE 与 RLS 都靠它，绝不能省
    seq: Mapped[int] = mapped_column(Integer)  # 文档内块序（0 起），切块函数的输出顺序
    text: Mapped[str] = mapped_column(Text)
    # 断点续传谓词列：NULL=待回填。写入/读回都是 list[float]（pgvector 0.5 纯文本编解码、零传递依赖）；
    # M3.5 检索走裸 SQL 距离算子，不依赖 ORM 读回形状
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMS), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 回填时写；换模型灰度列
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("document_id", "seq", name="uq_chunks_document_seq"),)

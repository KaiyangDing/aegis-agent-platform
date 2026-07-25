"""documents text 原文列

Revision ID: c28efda87e6a
Revises: 7fe5de25a9ca
Create Date: 2026-07-24 21:30:15.741729

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c28efda87e6a"
down_revision: str | Sequence[str] | None = "7fe5de25a9ca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """documents 补原文列（交付③偏差(23)）：任务 wire 契约只带 (document_id, tenant_id)
    ——计划钉死的签名——原文必须有持久居所；文档级事实归 documents（P6 口径自洽）。
    server_default='' 让既有行与省列插入合法（表当前为空，默认值纯防御）。"""
    op.add_column("documents", sa.Column("text", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("documents", "text")

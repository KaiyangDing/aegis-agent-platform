"""eval_cases/eval_runs 评测双表

Revision ID: b371c327f9ff
Revises: d41be6a90c27
Create Date: 2026-08-03 15:26:17.135088

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b371c327f9ff"
down_revision: str | Sequence[str] | None = "d41be6a90c27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """评测双表 + eval_cases RLS（M3.3 前置义务：新表迁移自带 ENABLE+策略，
    DEFAULT PRIVILEGES 只授 DML 不给 RLS）；eval_runs 无 tenant_id 列不上（events 先例）。"""
    op.create_table(
        "eval_cases",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expectation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_eval_cases_tenant_id"), "eval_cases", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_eval_cases_category"), "eval_cases", ["category"], unique=False)
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("judge_model", sa.String(length=64), nullable=True),
        sa.Column("answer_digest", sa.Text(), nullable=True),
        sa.Column("judge_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_eval_runs_batch_id"), "eval_runs", ["batch_id"], unique=False)
    op.create_index(op.f("ix_eval_runs_case_id"), "eval_runs", ["case_id"], unique=False)
    op.create_index("ix_eval_runs_case_created", "eval_runs", ["case_id", "created_at"], unique=False)
    op.execute("ALTER TABLE eval_cases ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON eval_cases "
        "USING (tenant_id = current_setting('app.tenant_id', true)) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
    )


def downgrade() -> None:
    """两表整撤（策略/索引随表删除）。"""
    op.drop_table("eval_runs")
    op.drop_table("eval_cases")

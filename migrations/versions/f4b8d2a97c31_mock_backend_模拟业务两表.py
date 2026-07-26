"""mock backend 模拟业务两表

Revision ID: f4b8d2a97c31
Revises: c28efda87e6a
Create Date: 2026-07-25 20:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f4b8d2a97c31"
down_revision: str | Sequence[str] | None = "c28efda87e6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RLS_TABLES = ["mock_orders", "mock_write_ops"]
# f-string 拼表名安全的前提：名单是本模块常量，不来自任何输入（c895f9007bf7 同款声明）


def upgrade() -> None:
    """两表 + RLS（前置义务：DEFAULT PRIVILEGES 只授 DML，RLS 必须每表自补——14c 登记）。"""
    op.create_table(
        "mock_orders",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("paid_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mock_orders_tenant_id"), "mock_orders", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_mock_orders_user_id"), "mock_orders", ["user_id"], unique=False)
    op.create_table(
        "mock_write_ops",
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("idempotency_key"),
    )
    op.create_index(op.f("ix_mock_write_ops_tenant_id"), "mock_write_ops", ["tenant_id"], unique=False)
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = current_setting('app.tenant_id', true)) "
            f"WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )


def downgrade() -> None:
    """两表整撤（策略/索引随表删除）。"""
    op.drop_table("mock_write_ops")
    op.drop_table("mock_orders")

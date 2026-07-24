"""rls 低权角色与租户隔离策略

Revision ID: c895f9007bf7
Revises: 6304edbb4760
Create Date: 2026-07-24 17:36:21.548376

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c895f9007bf7"
down_revision: str | Sequence[str] | None = "6304edbb4760"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RLS_TABLES = [
    ("tenants", "id"),  # 租户表自身：行主键即租户 id
    ("users", "tenant_id"),
    ("sessions", "tenant_id"),
    ("approvals", "tenant_id"),
    ("usage_ledger", "tenant_id"),
]
# f-string 拼表名安全的前提：名单是本模块常量，不来自任何输入


def upgrade() -> None:
    """低权角色 + 五表 RLS（P5 拍板：仅带 tenant_id 列的表；M3.4/M3.7 新表在各自迁移补）。"""
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'aegis_app') THEN
                CREATE ROLE aegis_app LOGIN PASSWORD 'aegis_app';
            END IF;
        END $$;
        """
    )  # dev 口令；生产走 secrets（02 §5 备份口径同款声明）。角色是库全局对象，幂等创建
    op.execute("GRANT USAGE ON SCHEMA public TO aegis_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aegis_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO aegis_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aegis_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO aegis_app")
    for table, column in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({column} = current_setting('app.tenant_id', true)) "
            f"WITH CHECK ({column} = current_setting('app.tenant_id', true))"
        )


def downgrade() -> None:
    """撤策略与授权；角色本身保留（幂等设计——重复升降不冲突）。"""
    for table, _ in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM aegis_app"
    )
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM aegis_app")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM aegis_app")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM aegis_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM aegis_app")

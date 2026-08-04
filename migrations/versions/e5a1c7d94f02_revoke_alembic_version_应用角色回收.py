"""revoke alembic_version from aegis_app（M4.7 观察池 ③）

Revision ID: e5a1c7d94f02
Revises: b371c327f9ff
Create Date: 2026-08-03

M3.3 的 `GRANT ON ALL TABLES` 把迁移簿记表 alembic_version 一并授给了低权应用角色，
且该表无租户列不在 RLS 名单——aegis_app 可读可改迁移水位（改水位=让下次 upgrade
从错误位置重放，属基础设施完整性面）。应用运行时没有任何路径需要碰它：全额回收，
"粗粒度授权换维护便利"的代价在此付清。DEFAULT PRIVILEGES 不动：它只影响未来新表，
业务新表按 M3.3 前置义务自带 RLS，与本表无关。证人：tests/test_rls.py M4.7 增量节。
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5a1c7d94f02"
down_revision: str | Sequence[str] | None = "b371c327f9ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("REVOKE ALL ON TABLE alembic_version FROM aegis_app")


def downgrade() -> None:
    # 还原 M3.3 GRANT ON ALL TABLES 波及本表时的权限集（DML 四件——授权面与 c895f9007bf7:42 同形）
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE alembic_version TO aegis_app")

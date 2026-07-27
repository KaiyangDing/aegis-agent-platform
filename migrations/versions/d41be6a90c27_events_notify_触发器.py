"""events notify 触发器

Revision ID: d41be6a90c27
Revises: f4b8d2a97c31
Create Date: 2026-07-26

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d41be6a90c27"
down_revision: str | Sequence[str] | None = "f4b8d2a97c31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """C22 实装（D10）：事务提交即通知、与事实源同生命周期——不给 Redis 加新降级面。
    payload=session_id:seq 只是路由键：消费方按 session 分发唤醒后一律重查增量，
    绝不消费通知内容（伪唤醒/丢通知皆无害）。RETURN NULL：AFTER 触发器返回值无意义。"""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION notify_aegis_event() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('aegis_events', NEW.session_id || ':' || NEW.seq);
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_events_notify AFTER INSERT ON events
        FOR EACH ROW EXECUTE FUNCTION notify_aegis_event()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_events_notify ON events")
    op.execute("DROP FUNCTION IF EXISTS notify_aegis_event()")

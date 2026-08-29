"""Preserve source timezone on timeline episodes.

Revision ID: 012
Revises: 011
"""

import sqlalchemy as sa

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "timeline_entries",
        sa.Column("timezone", sa.String(), nullable=False, server_default="UTC"),
    )
    op.execute("""
        UPDATE timeline_entries t
        SET timezone = COALESCE((
            SELECT rl.client_timezone
            FROM events e
            JOIN raw_logs rl ON rl.id = e.source_log_id
            WHERE e.session_id = t.session_id
              AND rl.client_timezone IS NOT NULL
            ORDER BY e.start_time
            LIMIT 1
        ), 'UTC')
    """)


def downgrade() -> None:
    op.drop_column("timeline_entries", "timezone")

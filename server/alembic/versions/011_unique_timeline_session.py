"""Guarantee one current timeline entry per session.

Revision ID: 011
Revises: 010
"""

import sqlalchemy as sa

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY session_id ORDER BY created_at, id
                   ) AS rn
            FROM timeline_entries
            WHERE session_id IS NOT NULL
        )
        DELETE FROM search_documents d
        USING ranked
        WHERE ranked.rn > 1
          AND d.source_type = 'timeline'
          AND d.source_id = ranked.id
    """)
    op.execute("""
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY session_id ORDER BY created_at, id
                   ) AS rn
            FROM timeline_entries
            WHERE session_id IS NOT NULL
        )
        DELETE FROM timeline_entries t
        USING ranked
        WHERE ranked.rn > 1 AND t.id = ranked.id
    """)
    op.create_index(
        "uq_timeline_entries_session",
        "timeline_entries",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("session_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_timeline_entries_session", table_name="timeline_entries")

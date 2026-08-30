"""
Switch datetime columns to TIMESTAMPTZ (timezone-aware)

Revision ID: 20251023_01_timestamptz_migration
Revises: b872d2e04e4a
Create Date: 2025-10-23
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251023_01'
down_revision = 'b872d2e04e4a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Convert timestamp without time zone to timestamptz, assuming stored values are UTC
    conn = op.get_bind()
    tables_cols = [
        ("rawlog", "ingested_at"),
        ("device", "last_seen"),
        ("event", "start_time"),
        ("event", "end_time"),
        ("eventmetadata", "created_at"),
        ("aiusagelog", "created_at"),
        ("synthesisreport", "created_at"),
        ("actorprocessinglog", "processed_at"),
        ("synthesisreport", "start_time"),
        ("synthesisreport", "end_time"),
    ]
    for table, col in tables_cols:
        try:
            op.execute(
                sa.text(
                    f"ALTER TABLE {table} ALTER COLUMN {col} TYPE TIMESTAMPTZ USING ({col} AT TIME ZONE 'UTC')"
                )
            )
        except Exception as e:
            # Some columns may not exist depending on migration state; continue
            print(f"Warning: could not alter {table}.{col} to timestamptz: {e}")


def downgrade() -> None:
    # Convert timestamptz back to timestamp without time zone, keeping UTC wall time
    tables_cols = [
        ("rawlog", "ingested_at"),
        ("device", "last_seen"),
        ("event", "start_time"),
        ("event", "end_time"),
        ("eventmetadata", "created_at"),
        ("aiusagelog", "created_at"),
        ("synthesisreport", "created_at"),
        ("actorprocessinglog", "processed_at"),
        ("synthesisreport", "start_time"),
        ("synthesisreport", "end_time"),
    ]
    for table, col in tables_cols:
        try:
            op.execute(
                sa.text(
                    f"ALTER TABLE {table} ALTER COLUMN {col} TYPE TIMESTAMP WITHOUT TIME ZONE USING ({col} AT TIME ZONE 'UTC')"
                )
            )
        except Exception as e:
            print(f"Warning: could not revert {table}.{col} to timestamp without time zone: {e}")

"""Carry explicit ownership through event and timeline memory.

Revision ID: 015
Revises: 014
"""

import sqlalchemy as sa

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("raw_logs", "events", "sessions", "timeline_entries"):
        op.add_column(table, sa.Column("owner_user_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_owner_user_id_users",
            table,
            "users",
            ["owner_user_id"],
            ["id"],
        )
        op.create_index(f"ix_{table}_owner_user_id", table, ["owner_user_id"])

    op.execute("""
        UPDATE raw_logs
        SET owner_user_id = COALESCE(
            (
                SELECT source_connections.user_id
                FROM source_connections
                WHERE source_connections.id = raw_logs.source_connection_id
            ),
            (
                SELECT devices.user_id
                FROM devices
                WHERE devices.id = raw_logs.device_id
            )
        )
        WHERE owner_user_id IS NULL
    """)
    op.execute("""
        UPDATE events
        SET owner_user_id = (
            SELECT raw_logs.owner_user_id
            FROM raw_logs
            WHERE raw_logs.id = events.source_log_id
        )
        WHERE owner_user_id IS NULL
    """)
    op.execute("""
        UPDATE sessions
        SET owner_user_id = (
            SELECT (array_agg(events.owner_user_id) FILTER (WHERE events.owner_user_id IS NOT NULL))[1]
            FROM events
            WHERE events.session_id = sessions.id
            HAVING COUNT(DISTINCT events.owner_user_id) = 1
        )
        WHERE owner_user_id IS NULL
    """)
    op.execute("""
        UPDATE timeline_entries
        SET owner_user_id = (
            SELECT sessions.owner_user_id
            FROM sessions
            WHERE sessions.id = timeline_entries.session_id
        )
        WHERE owner_user_id IS NULL
    """)

    op.add_column(
        "daily_summaries",
        sa.Column("id", sa.Uuid(), nullable=True, server_default=sa.text("gen_random_uuid()")),
    )
    op.add_column("daily_summaries", sa.Column("owner_user_id", sa.Uuid(), nullable=True))
    op.execute("""
        UPDATE daily_summaries
        SET owner_user_id = (
            SELECT (
                array_agg(timeline_entries.owner_user_id)
                FILTER (WHERE timeline_entries.owner_user_id IS NOT NULL)
            )[1]
            FROM timeline_entries
            WHERE timeline_entries.logical_date = daily_summaries.logical_date
            HAVING COUNT(DISTINCT timeline_entries.owner_user_id) = 1
        )
        WHERE owner_user_id IS NULL
    """)
    op.drop_constraint("daily_summaries_pkey", "daily_summaries", type_="primary")
    op.alter_column("daily_summaries", "id", nullable=False, server_default=None)
    op.create_primary_key("daily_summaries_pkey", "daily_summaries", ["id"])
    op.create_foreign_key(
        "fk_daily_summaries_owner_user_id_users",
        "daily_summaries",
        "users",
        ["owner_user_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_daily_summary_owner_date",
        "daily_summaries",
        ["owner_user_id", "logical_date"],
    )
    op.create_index(
        "ix_daily_summaries_owner_user_id",
        "daily_summaries",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_daily_summaries_logical_date",
        "daily_summaries",
        ["logical_date"],
    )
    op.create_index(
        "ix_daily_summaries_owner_date",
        "daily_summaries",
        ["owner_user_id", "logical_date"],
    )


def downgrade() -> None:
    # The old schema could store only one user's summary per date. Keep one
    # deterministic row per date if rollback is explicitly requested.
    op.execute("""
        DELETE FROM daily_summaries newer
        USING daily_summaries older
        WHERE newer.logical_date = older.logical_date
          AND newer.created_at > older.created_at
    """)
    op.drop_index("ix_daily_summaries_owner_date", table_name="daily_summaries")
    op.drop_index("ix_daily_summaries_logical_date", table_name="daily_summaries")
    op.drop_index("ix_daily_summaries_owner_user_id", table_name="daily_summaries")
    op.drop_constraint("uq_daily_summary_owner_date", "daily_summaries", type_="unique")
    op.drop_constraint(
        "fk_daily_summaries_owner_user_id_users",
        "daily_summaries",
        type_="foreignkey",
    )
    op.drop_constraint("daily_summaries_pkey", "daily_summaries", type_="primary")
    op.create_primary_key("daily_summaries_pkey", "daily_summaries", ["logical_date"])
    op.drop_column("daily_summaries", "owner_user_id")
    op.drop_column("daily_summaries", "id")

    for table in ("timeline_entries", "sessions", "events", "raw_logs"):
        op.drop_index(f"ix_{table}_owner_user_id", table_name=table)
        op.drop_constraint(
            f"fk_{table}_owner_user_id_users",
            table,
            type_="foreignkey",
        )
        op.drop_column(table, "owner_user_id")

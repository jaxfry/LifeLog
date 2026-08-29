"""Make canonical kernel facts explicitly owner scoped.

Revision ID: 016
Revises: 015
"""

import sqlalchemy as sa

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("relations", "measurements"):
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
        UPDATE relations
        SET owner_user_id = COALESCE(
            CASE WHEN subject_type = 'entity' THEN (
                SELECT entities.owner_user_id FROM entities WHERE entities.id = relations.subject_id
            ) END,
            CASE WHEN object_type = 'entity' THEN (
                SELECT entities.owner_user_id FROM entities WHERE entities.id = relations.object_id
            ) END,
            (
                SELECT events.owner_user_id FROM events WHERE events.id = relations.source_event_id
            ),
            (
                SELECT file_attachments.owner_user_id
                FROM file_attachments
                WHERE file_attachments.id = relations.source_file_id
            )
        )
        WHERE owner_user_id IS NULL
    """)
    op.execute("""
        UPDATE measurements
        SET owner_user_id = (
            SELECT entities.owner_user_id
            FROM entities
            WHERE entities.id = measurements.entity_id
        )
        WHERE owner_user_id IS NULL
    """)


def downgrade() -> None:
    for table in ("measurements", "relations"):
        op.drop_index(f"ix_{table}_owner_user_id", table_name=table)
        op.drop_constraint(
            f"fk_{table}_owner_user_id_users",
            table,
            type_="foreignkey",
        )
        op.drop_column(table, "owner_user_id")

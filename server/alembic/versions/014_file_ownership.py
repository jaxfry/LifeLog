"""Make file evidence explicitly owner scoped.

Revision ID: 014
Revises: 013
"""

import sqlalchemy as sa

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("file_attachments", sa.Column("owner_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_file_attachments_owner_user_id_users",
        "file_attachments",
        "users",
        ["owner_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_file_attachments_owner_user_id",
        "file_attachments",
        ["owner_user_id"],
    )
    # Captures have always been owner scoped. This safely upgrades all files
    # already connected to a capture without guessing ownership for older,
    # standalone records.
    op.execute("""
        UPDATE file_attachments
        SET owner_user_id = (
            SELECT captures.user_id
            FROM capture_artifacts
            JOIN captures ON captures.id = capture_artifacts.capture_id
            WHERE capture_artifacts.file_id = file_attachments.id
            LIMIT 1
        )
        WHERE owner_user_id IS NULL
          AND EXISTS (
            SELECT 1
            FROM capture_artifacts
            WHERE capture_artifacts.file_id = file_attachments.id
          )
    """)
    for table in ("commitments", "notifications", "commitment_progress", "plan_blocks"):
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
        UPDATE commitments
        SET owner_user_id = (
            SELECT file_attachments.owner_user_id
            FROM file_attachments
            WHERE file_attachments.id = commitments.source_file_id
        )
        WHERE owner_user_id IS NULL AND source_file_id IS NOT NULL
    """)
    for table in ("notifications", "commitment_progress", "plan_blocks"):
        op.execute(f"""
            UPDATE {table}
            SET owner_user_id = (
                SELECT commitments.owner_user_id
                FROM commitments
                WHERE commitments.id = {table}.commitment_id
            )
            WHERE owner_user_id IS NULL
        """)
    op.add_column("ai_usage", sa.Column("owner_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_ai_usage_owner_user_id_users",
        "ai_usage",
        "users",
        ["owner_user_id"],
        ["id"],
    )
    op.create_index("ix_ai_usage_owner_user_id", "ai_usage", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_owner_user_id", table_name="ai_usage")
    op.drop_constraint(
        "fk_ai_usage_owner_user_id_users",
        "ai_usage",
        type_="foreignkey",
    )
    op.drop_column("ai_usage", "owner_user_id")
    for table in ("plan_blocks", "commitment_progress", "notifications", "commitments"):
        op.drop_index(f"ix_{table}_owner_user_id", table_name=table)
        op.drop_constraint(
            f"fk_{table}_owner_user_id_users",
            table,
            type_="foreignkey",
        )
        op.drop_column(table, "owner_user_id")
    op.drop_index("ix_file_attachments_owner_user_id", table_name="file_attachments")
    op.drop_constraint(
        "fk_file_attachments_owner_user_id_users",
        "file_attachments",
        type_="foreignkey",
    )
    op.drop_column("file_attachments", "owner_user_id")

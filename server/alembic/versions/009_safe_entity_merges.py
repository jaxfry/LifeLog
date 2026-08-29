"""Add owned, source-aware entities and reversible merge records.

Revision ID: 009
Revises: 008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("entities", sa.Column("owner_user_id", sa.Uuid(), nullable=True))
    op.add_column("entities", sa.Column("identity_namespace", sa.String(), nullable=True))
    op.add_column("entities", sa.Column("external_identity", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_entities_owner_user_id_users",
        "entities",
        "users",
        ["owner_user_id"],
        ["id"],
    )
    op.create_index("ix_entities_owner_user_id", "entities", ["owner_user_id"])
    op.create_index("ix_entities_identity_namespace", "entities", ["identity_namespace"])
    op.create_index("ix_entities_external_identity", "entities", ["external_identity"])
    # Preserve the common self-hosted, single-owner upgrade path without
    # guessing ownership in a multi-user database.
    op.execute(
        sa.text(
            "UPDATE entities SET owner_user_id = (SELECT id FROM users LIMIT 1) "
            "WHERE owner_user_id IS NULL AND (SELECT count(*) FROM users) = 1"
        )
    )
    op.drop_index("uq_entities_current_canonical_key", table_name="entities")
    op.create_index(
        "ix_entities_owner_current_name",
        "entities",
        ["owner_user_id", "entity_type", "canonical_key"],
        unique=False,
        postgresql_where=sa.text("is_superseded = false AND canonical_key IS NOT NULL"),
    )
    op.create_index(
        "uq_entities_current_external_identity",
        "entities",
        [
            "owner_user_id",
            "entity_type",
            "identity_namespace",
            "external_identity",
        ],
        unique=True,
        postgresql_where=sa.text(
            "is_superseded = false AND owner_user_id IS NOT NULL "
            "AND identity_namespace IS NOT NULL AND external_identity IS NOT NULL"
        ),
    )

    op.create_table(
        "entity_merges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("survivor_id", sa.Uuid(), nullable=False),
        sa.Column("merged_id", sa.Uuid(), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("review_item_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reversed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('applied','reversed')", name="ck_entity_merges_status"),
        sa.ForeignKeyConstraint(["survivor_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["merged_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "survivor_id",
        "merged_id",
        "decided_by_user_id",
        "review_item_id",
        "status",
    ):
        op.create_index(f"ix_entity_merges_{column}", "entity_merges", [column])
    op.create_index("ix_entity_merges_survivor", "entity_merges", ["survivor_id", "status"])
    op.create_index("ix_entity_merges_merged", "entity_merges", ["merged_id", "status"])


def downgrade() -> None:
    op.drop_table("entity_merges")
    op.drop_index("uq_entities_current_external_identity", table_name="entities")
    op.drop_index("ix_entities_owner_current_name", table_name="entities")
    op.create_index(
        "uq_entities_current_canonical_key",
        "entities",
        ["entity_type", "canonical_key"],
        unique=True,
        postgresql_where=sa.text("is_superseded = false AND canonical_key IS NOT NULL"),
    )
    op.drop_index("ix_entities_external_identity", table_name="entities")
    op.drop_index("ix_entities_identity_namespace", table_name="entities")
    op.drop_index("ix_entities_owner_user_id", table_name="entities")
    op.drop_constraint("fk_entities_owner_user_id_users", "entities", type_="foreignkey")
    op.drop_column("entities", "external_identity")
    op.drop_column("entities", "identity_namespace")
    op.drop_column("entities", "owner_user_id")

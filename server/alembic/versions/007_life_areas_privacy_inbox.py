"""Add Life Areas, scoped privacy policies, and unified review Inbox.

Revision ID: 007
Revises: 006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "life_areas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(), nullable=True),
        sa.Column("color", sa.String(), nullable=True),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "slug", name="uq_life_area_user_slug"),
    )
    for column in ("user_id", "slug", "is_active"):
        op.create_index(f"ix_life_areas_{column}", "life_areas", [column])
    op.create_index("ix_life_areas_user_active", "life_areas", ["user_id", "is_active"])

    op.create_table(
        "context_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("life_area_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_context_links_confidence"),
        sa.ForeignKeyConstraint(["life_area_id"], ["life_areas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("life_area_id", "target_type", "target_id", name="uq_context_link_target"),
    )
    for column in ("life_area_id", "target_type", "target_id"):
        op.create_index(f"ix_context_links_{column}", "context_links", [column])
    op.create_index("ix_context_links_target", "context_links", ["target_type", "target_id"])

    op.create_table(
        "memory_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("allowed_area_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sensitivity", sa.String(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "visibility IN ('global','selected_areas','private')",
            name="ck_memory_policies_visibility",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "target_type", "target_id", name="uq_memory_policy_target"),
    )
    for column in ("user_id", "target_type", "target_id", "visibility", "sensitivity"):
        op.create_index(f"ix_memory_policies_{column}", "memory_policies", [column])

    op.create_table(
        "review_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("capture_id", sa.Uuid(), nullable=True),
        sa.Column("life_area_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("consequential", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','accepted','rejected','dismissed')",
            name="ck_review_items_status",
        ),
        sa.ForeignKeyConstraint(["capture_id"], ["captures.id"]),
        sa.ForeignKeyConstraint(["life_area_id"], ["life_areas.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source_type", "source_id", name="uq_review_item_source"),
    )
    for column in (
        "user_id",
        "kind",
        "source_type",
        "source_id",
        "capture_id",
        "life_area_id",
        "consequential",
        "status",
    ):
        op.create_index(f"ix_review_items_{column}", "review_items", [column])
    op.create_index("ix_review_items_user_status", "review_items", ["user_id", "status"])


def downgrade() -> None:
    op.drop_table("review_items")
    op.drop_table("memory_policies")
    op.drop_table("context_links")
    op.drop_table("life_areas")

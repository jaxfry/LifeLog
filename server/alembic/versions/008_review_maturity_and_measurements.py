"""Add review item maturity fields, decision history, and numeric measurements.

Revision ID: 008
Revises: 007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("review_items", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column(
        "review_items",
        sa.Column("priority", sa.String(), nullable=False, server_default="normal"),
    )
    op.add_column("review_items", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.add_column(
        "review_items",
        sa.Column("choices", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    op.create_check_constraint(
        "ck_review_items_priority",
        "review_items",
        "priority IN ('low','normal','high')",
    )
    op.create_index("ix_review_items_priority", "review_items", ["priority"])

    op.create_table(
        "review_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_item_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"]),
    )
    op.create_index("ix_review_decisions_review_item_id", "review_decisions", ["review_item_id"])

    op.create_table(
        "measurements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("value_text", sa.String(), nullable=True),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_event_id", sa.Uuid(), nullable=True),
        sa.Column("source_file_id", sa.Uuid(), nullable=True),
        sa.Column("extractor", sa.String(), nullable=True),
        sa.Column("extraction_version", sa.Integer(), nullable=True),
        sa.Column("is_superseded", sa.Boolean(), nullable=False),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["source_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["source_file_id"], ["file_attachments.id"]),
        sa.ForeignKeyConstraint(["superseded_by"], ["measurements.id"]),
    )
    op.create_check_constraint(
        "ck_measurements_confidence",
        "measurements",
        "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
    )
    op.create_check_constraint(
        "ck_measurements_value_present",
        "measurements",
        "value IS NOT NULL OR value_text IS NOT NULL",
    )
    op.create_index("ix_measurements_entity_id", "measurements", ["entity_id"])
    op.create_index("ix_measurements_metric", "measurements", ["metric"])
    op.create_index("ix_measurements_is_superseded", "measurements", ["is_superseded"])
    op.create_index("ix_measurements_entity_metric", "measurements", ["entity_id", "metric"])
    op.create_unique_constraint(
        "uq_measurement_extracted",
        "measurements",
        ["source_event_id", "entity_id", "metric", "extractor", "extraction_version"],
    )
    op.create_unique_constraint(
        "uq_measurement_extracted_non_event",
        "measurements",
        ["source_file_id", "entity_id", "metric", "extractor", "extraction_version"],
    )


def downgrade() -> None:
    op.drop_table("measurements")
    op.drop_table("review_decisions")
    op.drop_index("ix_review_items_priority", table_name="review_items")
    op.drop_constraint("ck_review_items_priority", "review_items", type_="check")
    op.drop_column("review_items", "choices")
    op.drop_column("review_items", "expires_at")
    op.drop_column("review_items", "priority")
    op.drop_column("review_items", "confidence")

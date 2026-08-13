"""kernel: entities and relations

Revision ID: 003
Revises: 002
Create Date: 2026-08-12 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "003"
down_revision: str | Sequence[str] | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("canonical_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("is_superseded", sa.Boolean(), nullable=False),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["superseded_by"], ["entities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_entities_confidence",
        ),
    )
    op.create_index(op.f("ix_entities_entity_type"), "entities", ["entity_type"], unique=False)
    op.create_index(op.f("ix_entities_is_superseded"), "entities", ["is_superseded"], unique=False)
    op.create_index(op.f("ix_entities_canonical_key"), "entities", ["canonical_key"], unique=False)
    op.create_index(
        "uq_entities_current_canonical_key",
        "entities",
        ["entity_type", "canonical_key"],
        unique=True,
        postgresql_where=sa.text("is_superseded = false AND canonical_key IS NOT NULL"),
    )
    op.create_table(
        "relations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("predicate", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=False),
        sa.Column("object_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("occurred_from", sa.DateTime(), nullable=True),
        sa.Column("occurred_until", sa.DateTime(), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("is_superseded", sa.Boolean(), nullable=False),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.Column("source_event_id", sa.Uuid(), nullable=True),
        sa.Column("extractor", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("extraction_version", sa.Integer(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "object_type IN ('entity','event')",
            name="ck_relations_object_type",
        ),
        sa.CheckConstraint(
            "subject_type IN ('entity','event')",
            name="ck_relations_subject_type",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_relations_confidence",
        ),
        sa.CheckConstraint(
            "occurred_until IS NULL OR occurred_from IS NULL OR occurred_until >= occurred_from",
            name="ck_relations_occurred_window",
        ),
        sa.ForeignKeyConstraint(["source_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["superseded_by"], ["relations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_relations_is_superseded"), "relations", ["is_superseded"], unique=False)
    op.create_index(op.f("ix_relations_object_id"), "relations", ["object_id"], unique=False)
    op.create_index(op.f("ix_relations_subject_id"), "relations", ["subject_id"], unique=False)
    op.create_index(
        op.f("ix_relations_subject_predicate"),
        "relations",
        ["subject_id", "predicate"],
        unique=False,
    )
    op.create_index(
        op.f("ix_relations_object_predicate"),
        "relations",
        ["object_id", "predicate"],
        unique=False,
    )
    op.create_index(op.f("ix_relations_source_event"), "relations", ["source_event_id"], unique=False)
    op.create_index(
        "uq_relations_extracted_fact",
        "relations",
        ["source_event_id", "subject_id", "predicate", "object_id", "extractor", "extraction_version"],
        unique=True,
        postgresql_where=sa.text("source_event_id IS NOT NULL"),
    )
    op.add_column("events", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("events", sa.Column("memory_extraction_version", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_events_memory_extraction_version"),
        "events",
        ["memory_extraction_version"],
        unique=False,
    )
    op.add_column(
        "events",
        sa.Column("superseded_by", sa.Uuid(), sa.ForeignKey("events.id"), nullable=True),
    )
    op.add_column(
        "extensions",
        sa.Column(
            "api_version",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "extensions",
        sa.Column("archived_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("extensions", "archived_at")
    op.drop_column("extensions", "api_version")
    op.drop_column("events", "superseded_by")
    op.drop_index(op.f("ix_events_memory_extraction_version"), table_name="events")
    op.drop_column("events", "memory_extraction_version")
    op.drop_column("events", "confidence")
    op.drop_index("uq_relations_extracted_fact", table_name="relations")
    op.drop_index(op.f("ix_relations_source_event"), table_name="relations")
    op.drop_index(op.f("ix_relations_object_predicate"), table_name="relations")
    op.drop_index(op.f("ix_relations_subject_id"), table_name="relations")
    op.drop_index(op.f("ix_relations_subject_predicate"), table_name="relations")
    op.drop_index(op.f("ix_relations_object_id"), table_name="relations")
    op.drop_index(op.f("ix_relations_is_superseded"), table_name="relations")
    op.drop_table("relations")
    op.drop_index("uq_entities_current_canonical_key", table_name="entities")
    op.drop_index(op.f("ix_entities_canonical_key"), table_name="entities")
    op.drop_index(op.f("ix_entities_is_superseded"), table_name="entities")
    op.drop_index(op.f("ix_entities_entity_type"), table_name="entities")
    op.drop_table("entities")

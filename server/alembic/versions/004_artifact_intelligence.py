"""artifact intelligence, commitments, and grounded memory

Revision ID: 004
Revises: 003
Create Date: 2026-08-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "004"
down_revision: str | Sequence[str] | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entity_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("canonical_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id", "canonical_key", name="uq_entity_alias_key"),
    )
    op.create_index(op.f("ix_entity_aliases_entity_id"), "entity_aliases", ["entity_id"], unique=False)
    op.create_index("ix_entity_aliases_canonical_key", "entity_aliases", ["canonical_key"], unique=False)

    op.create_table(
        "file_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filename", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("stored_path", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("mime_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("timeline_id", sa.Uuid(), nullable=True),
        sa.Column("category", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("ai_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("user_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("technical_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_processed", sa.Boolean(), nullable=False),
        sa.Column("processing_status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("processing_version", sa.Integer(), nullable=False),
        sa.Column("processing_error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("source_extension_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["source_extension_id"], ["extensions.id"]),
        sa.ForeignKeyConstraint(["timeline_id"], ["timeline_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "processing_status IN ('pending','processing','ready','failed')",
            name="ck_file_attachments_processing_status",
        ),
    )
    for column in ("content_hash", "event_id", "timeline_id", "category", "processing_status", "source_extension_id"):
        op.create_index(op.f(f"ix_file_attachments_{column}"), "file_attachments", [column], unique=False)

    op.add_column("ai_usage", sa.Column("operation", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("ai_usage", sa.Column("source_file_id", sa.Uuid(), nullable=True))
    op.add_column("ai_usage", sa.Column("source_event_id", sa.Uuid(), nullable=True))
    op.add_column("ai_usage", sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_foreign_key("fk_ai_usage_source_file", "ai_usage", "file_attachments", ["source_file_id"], ["id"])
    op.create_foreign_key("fk_ai_usage_source_event", "ai_usage", "events", ["source_event_id"], ["id"])
    for column in ("operation", "source_file_id", "source_event_id"):
        op.create_index(op.f(f"ix_ai_usage_{column}"), "ai_usage", [column], unique=False)

    op.create_table(
        "content_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("locator", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("processing_version", sa.Integer(), nullable=False),
        sa.Column("is_superseded", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["file_attachments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("sequence >= 0", name="ck_content_chunks_sequence"),
        sa.CheckConstraint("processing_version >= 1", name="ck_content_chunks_processing_version"),
        sa.UniqueConstraint("file_id", "processing_version", "sequence", name="uq_content_chunk_version_sequence"),
    )
    op.create_index(op.f("ix_content_chunks_file_id"), "content_chunks", ["file_id"], unique=False)
    op.create_index(op.f("ix_content_chunks_content_type"), "content_chunks", ["content_type"], unique=False)
    op.create_index(op.f("ix_content_chunks_is_superseded"), "content_chunks", ["is_superseded"], unique=False)
    op.create_index("ix_content_chunks_file_current", "content_chunks", ["file_id", "is_superseded"], unique=False)
    op.execute(
        "CREATE INDEX ix_content_chunks_search ON content_chunks "
        "USING gin (to_tsvector('simple', content))"
    )

    op.create_table(
        "memory_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("evidence_quote", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("extractor", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("extraction_version", sa.Integer(), nullable=False),
        sa.Column("promoted_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("kind IN ('entity','relation','commitment')", name="ck_memory_proposals_kind"),
        sa.CheckConstraint("status IN ('pending','accepted','rejected')", name="ck_memory_proposals_status"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_proposals_confidence"),
        sa.ForeignKeyConstraint(["file_id"], ["file_attachments.id"]),
        sa.ForeignKeyConstraint(["chunk_id"], ["content_chunks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("file_id", "chunk_id", "kind", "status", "promoted_id"):
        op.create_index(op.f(f"ix_memory_proposals_{column}"), "memory_proposals", [column], unique=False)

    op.create_table(
        "commitments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("not_before", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_file_id", sa.Uuid(), nullable=True),
        sa.Column("source_chunk_id", sa.Uuid(), nullable=True),
        sa.Column("source_event_id", sa.Uuid(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('suggested','planned','in_progress','completed','cancelled')",
            name="ck_commitments_status",
        ),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_commitments_confidence"),
        sa.CheckConstraint("due_at IS NULL OR not_before IS NULL OR due_at >= not_before", name="ck_commitments_window"),
        sa.ForeignKeyConstraint(["source_file_id"], ["file_attachments.id"]),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["content_chunks.id"]),
        sa.ForeignKeyConstraint(["source_event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("title", "status", "due_at", "source_file_id"):
        op.create_index(op.f(f"ix_commitments_{column}"), "commitments", [column], unique=False)

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("commitment_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("body", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('pending','delivered','dismissed','cancelled','failed')", name="ck_notifications_status"),
        sa.ForeignKeyConstraint(["commitment_id"], ["commitments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("commitment_id", "scheduled_for", "status"):
        op.create_index(op.f(f"ix_notifications_{column}"), "notifications", [column], unique=False)

    op.create_table(
        "commitment_progress",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("commitment_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("unit", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("note", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_progress_confidence"),
        sa.ForeignKeyConstraint(["commitment_id"], ["commitments.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("commitment_id", "event_id", "observed_at"):
        op.create_index(op.f(f"ix_commitment_progress_{column}"), "commitment_progress", [column], unique=False)

    op.create_table(
        "plan_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("commitment_id", sa.Uuid(), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("rationale", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("planner_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('suggested','accepted','completed','skipped','cancelled')",
            name="ck_plan_blocks_status",
        ),
        sa.CheckConstraint("end_at > start_at", name="ck_plan_blocks_window"),
        sa.ForeignKeyConstraint(["commitment_id"], ["commitments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("commitment_id", "start_at", "end_at", "status"):
        op.create_index(op.f(f"ix_plan_blocks_{column}"), "plan_blocks", [column], unique=False)

    op.add_column("relations", sa.Column("source_file_id", sa.Uuid(), nullable=True))
    op.add_column("relations", sa.Column("source_chunk_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_relations_source_file", "relations", "file_attachments", ["source_file_id"], ["id"])
    op.create_foreign_key("fk_relations_source_chunk", "relations", "content_chunks", ["source_chunk_id"], ["id"])
    op.create_index(op.f("ix_relations_source_file"), "relations", ["source_file_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_relations_source_file"), table_name="relations")
    op.drop_constraint("fk_relations_source_chunk", "relations", type_="foreignkey")
    op.drop_constraint("fk_relations_source_file", "relations", type_="foreignkey")
    op.drop_column("relations", "source_chunk_id")
    op.drop_column("relations", "source_file_id")
    for column in ("source_event_id", "source_file_id", "operation"):
        op.drop_index(op.f(f"ix_ai_usage_{column}"), table_name="ai_usage")
    op.drop_constraint("fk_ai_usage_source_event", "ai_usage", type_="foreignkey")
    op.drop_constraint("fk_ai_usage_source_file", "ai_usage", type_="foreignkey")
    op.drop_column("ai_usage", "data")
    op.drop_column("ai_usage", "source_event_id")
    op.drop_column("ai_usage", "source_file_id")
    op.drop_column("ai_usage", "operation")
    op.drop_table("commitment_progress")
    op.drop_table("plan_blocks")
    op.drop_table("notifications")
    op.drop_table("commitments")
    op.drop_table("memory_proposals")
    op.drop_index("ix_content_chunks_search", table_name="content_chunks")
    op.drop_table("content_chunks")
    op.drop_table("file_attachments")
    op.drop_table("entity_aliases")

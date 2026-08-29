"""Add grounded evidence, claims, and derivation lineage.

Revision ID: 013
Revises: d900ecdc383e
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "013"
down_revision = "d900ecdc383e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("source_file_id", sa.Uuid(), nullable=True),
        sa.Column("capture_id", sa.Uuid(), nullable=True),
        sa.Column("source_event_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("structure", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("source_content_hash", sa.String(), nullable=False),
        sa.Column("parser", sa.String(), nullable=False),
        sa.Column("parser_version", sa.String(), nullable=False),
        sa.Column("derivation_key", sa.String(), nullable=False),
        sa.Column("is_superseded", sa.Boolean(), nullable=False),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('document','image','transcript','note','event','structured')",
            name="ck_evidence_documents_kind",
        ),
        sa.ForeignKeyConstraint(["capture_id"], ["captures.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["source_file_id"], ["file_attachments.id"]),
        sa.ForeignKeyConstraint(["superseded_by"], ["evidence_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "derivation_key",
            name="uq_evidence_document_derivation",
        ),
    )
    op.create_index(
        "ix_evidence_documents_file_current",
        "evidence_documents",
        ["source_file_id", "is_superseded"],
    )
    op.create_index(
        "ix_evidence_documents_capture_current",
        "evidence_documents",
        ["capture_id", "is_superseded"],
    )
    _create_simple_indexes(
        "evidence_documents",
        "owner_user_id",
        "source_file_id",
        "capture_id",
        "source_event_id",
        "kind",
        "language",
        "source_content_hash",
        "derivation_key",
        "is_superseded",
        "superseded_by",
    )

    op.create_table(
        "evidence_spans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("source_chunk_id", sa.Uuid(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("bounding_box", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("start_seconds", sa.Float(), nullable=True),
        sa.Column("end_seconds", sa.Float(), nullable=True),
        sa.Column("speaker_label", sa.String(), nullable=True),
        sa.Column("structural_path", sa.String(), nullable=True),
        sa.Column("locator", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("sequence >= 0", name="ck_evidence_spans_sequence"),
        sa.CheckConstraint(
            "char_start IS NULL OR char_end IS NULL OR char_end >= char_start",
            name="ck_evidence_spans_character_range",
        ),
        sa.CheckConstraint(
            "start_seconds IS NULL OR end_seconds IS NULL OR end_seconds >= start_seconds",
            name="ck_evidence_spans_time_range",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["evidence_documents.id"]),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["content_chunks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "sequence", name="uq_evidence_span_sequence"),
        sa.UniqueConstraint("source_chunk_id", name="uq_evidence_span_source_chunk"),
    )
    op.create_index(
        "ix_evidence_spans_document_range",
        "evidence_spans",
        ["document_id", "char_start", "char_end"],
    )
    _create_simple_indexes(
        "evidence_spans",
        "document_id",
        "source_chunk_id",
        "page_number",
        "speaker_label",
        "content_hash",
    )

    op.create_table(
        "entity_mentions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("span_id", sa.Uuid(), nullable=False),
        sa.Column("surface_text", sa.String(), nullable=False),
        sa.Column("normalized_text", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("extractor", sa.String(), nullable=False),
        sa.Column("extraction_version", sa.Integer(), nullable=False),
        sa.Column("ontology_version", sa.String(), nullable=False),
        sa.Column("resolution_status", sa.String(), nullable=False),
        sa.Column("resolved_entity_id", sa.Uuid(), nullable=True),
        sa.Column("derivation_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "resolution_status IN ('unresolved','resolved','ambiguous','rejected')",
            name="ck_entity_mentions_resolution_status",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_entity_mentions_confidence",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_entity_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["span_id"], ["evidence_spans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "derivation_key",
            name="uq_entity_mention_derivation",
        ),
    )
    op.create_index(
        "ix_entity_mentions_owner_name",
        "entity_mentions",
        ["owner_user_id", "entity_type", "normalized_text"],
    )
    _create_simple_indexes(
        "entity_mentions",
        "owner_user_id",
        "span_id",
        "normalized_text",
        "entity_type",
        "resolution_status",
        "resolved_entity_id",
        "derivation_key",
    )

    op.create_table(
        "memory_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("subject_mention_id", sa.Uuid(), nullable=True),
        sa.Column("subject_entity_id", sa.Uuid(), nullable=True),
        sa.Column("predicate", sa.String(), nullable=False),
        sa.Column("object_mention_id", sa.Uuid(), nullable=True),
        sa.Column("object_entity_id", sa.Uuid(), nullable=True),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("polarity", sa.String(), nullable=False),
        sa.Column("modality", sa.String(), nullable=False),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_until", sa.DateTime(), nullable=True),
        sa.Column("time_precision", sa.String(), nullable=True),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("reconciliation_status", sa.String(), nullable=False),
        sa.Column("extractor", sa.String(), nullable=False),
        sa.Column("extraction_version", sa.Integer(), nullable=False),
        sa.Column("ontology_version", sa.String(), nullable=False),
        sa.Column("derivation_key", sa.String(), nullable=False),
        sa.Column("canonical_target_type", sa.String(), nullable=True),
        sa.Column("canonical_target_id", sa.Uuid(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("learned_at", sa.DateTime(), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('relation','attribute','measurement','commitment','classification','temporal')",
            name="ck_memory_claims_kind",
        ),
        sa.CheckConstraint("polarity IN ('positive','negative')", name="ck_memory_claims_polarity"),
        sa.CheckConstraint(
            "modality IN ('asserted','possible','planned','requested','inferred')",
            name="ck_memory_claims_modality",
        ),
        sa.CheckConstraint(
            "reconciliation_status IN ('pending','accepted','corroborating','conflicting',"
            "'superseded','rejected','review')",
            name="ck_memory_claims_reconciliation_status",
        ),
        sa.CheckConstraint(
            "extraction_confidence IS NULL OR "
            "(extraction_confidence >= 0 AND extraction_confidence <= 1)",
            name="ck_memory_claims_extraction_confidence",
        ),
        sa.CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)",
            name="ck_memory_claims_quality_score",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from",
            name="ck_memory_claims_valid_range",
        ),
        sa.ForeignKeyConstraint(["object_entity_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["object_mention_id"], ["entity_mentions.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["subject_entity_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["subject_mention_id"], ["entity_mentions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "derivation_key",
            name="uq_memory_claim_derivation",
        ),
    )
    op.create_index(
        "ix_memory_claims_owner_predicate",
        "memory_claims",
        ["owner_user_id", "predicate"],
    )
    op.create_index(
        "ix_memory_claims_owner_state",
        "memory_claims",
        ["owner_user_id", "reconciliation_status"],
    )
    _create_simple_indexes(
        "memory_claims",
        "owner_user_id",
        "kind",
        "subject_mention_id",
        "subject_entity_id",
        "predicate",
        "object_mention_id",
        "object_entity_id",
        "valid_from",
        "valid_until",
        "reconciliation_status",
        "derivation_key",
        "canonical_target_type",
        "canonical_target_id",
    )

    op.create_table(
        "claim_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("span_id", sa.Uuid(), nullable=True),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("source_record_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "role IN ('direct','context','contradiction','correction','user_confirmation')",
            name="ck_claim_evidence_role",
        ),
        sa.ForeignKeyConstraint(["claim_id"], ["memory_claims.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["source_record_id"], ["source_records.id"]),
        sa.ForeignKeyConstraint(["span_id"], ["evidence_spans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "claim_id",
            "span_id",
            "event_id",
            "source_record_id",
            "role",
            name="uq_claim_evidence_source",
        ),
    )
    op.create_index("ix_claim_evidence_claim", "claim_evidence", ["claim_id", "role"])
    _create_simple_indexes(
        "claim_evidence",
        "claim_id",
        "span_id",
        "event_id",
        "source_record_id",
    )

    op.create_table(
        "fact_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["memory_claims.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "target_type",
            "target_id",
            "claim_id",
            name="uq_fact_evidence_claim",
        ),
    )
    op.create_index(
        "ix_fact_evidence_target",
        "fact_evidence",
        ["target_type", "target_id"],
    )
    _create_simple_indexes("fact_evidence", "target_type", "target_id", "claim_id")

    op.create_table(
        "entity_resolution_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mention_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_entity_id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("components", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("model_role", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("review_item_id", sa.Uuid(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('accepted','rejected','review','superseded')",
            name="ck_entity_resolution_decisions_outcome",
        ),
        sa.CheckConstraint(
            "score >= 0 AND score <= 1",
            name="ck_entity_resolution_decisions_score",
        ),
        sa.ForeignKeyConstraint(["candidate_entity_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["mention_id"], ["entity_mentions.id"]),
        sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "mention_id",
            "candidate_entity_id",
            "method",
            name="uq_resolution_candidate_method",
        ),
    )
    _create_simple_indexes(
        "entity_resolution_decisions",
        "mention_id",
        "candidate_entity_id",
        "method",
        "outcome",
        "review_item_id",
    )

    op.create_table(
        "derivation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("derivation_key", sa.String(), nullable=False),
        sa.Column("input_fingerprint", sa.String(), nullable=False),
        sa.Column("processor", sa.String(), nullable=False),
        sa.Column("processor_version", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("ontology_version", sa.String(), nullable=True),
        sa.Column("model_role", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("policy_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("budget_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed','skipped','cancelled')",
            name="ck_derivation_runs_status",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "derivation_key", name="uq_derivation_run_key"),
    )
    op.create_index(
        "ix_derivation_runs_owner_purpose",
        "derivation_runs",
        ["owner_user_id", "purpose", "status"],
    )
    _create_simple_indexes(
        "derivation_runs",
        "owner_user_id",
        "purpose",
        "target_type",
        "target_id",
        "derivation_key",
        "input_fingerprint",
        "status",
    )

    op.create_table(
        "derivation_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("derivation_run_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["derivation_run_id"], ["derivation_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "derivation_run_id",
            "attempt",
            name="uq_derivation_attempt_number",
        ),
    )
    _create_simple_indexes("derivation_attempts", "derivation_run_id", "status")

    op.create_table(
        "dirty_scopes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("occurred_from", sa.DateTime(), nullable=True),
        sa.Column("occurred_until", sa.DateTime(), nullable=True),
        sa.Column("entity_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dependency_hash", sa.String(), nullable=False),
        sa.Column("materiality", sa.Float(), nullable=False),
        sa.Column("quiet_until", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','queued','running','resolved','cancelled')",
            name="ck_dirty_scopes_status",
        ),
        sa.CheckConstraint(
            "materiality >= 0 AND materiality <= 1",
            name="ck_dirty_scopes_materiality",
        ),
        sa.CheckConstraint(
            "occurred_until IS NULL OR occurred_from IS NULL OR occurred_until >= occurred_from",
            name="ck_dirty_scopes_time_range",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dirty_scopes_owner_status",
        "dirty_scopes",
        ["owner_user_id", "status", "quiet_until"],
    )
    _create_simple_indexes(
        "dirty_scopes",
        "owner_user_id",
        "reason",
        "occurred_from",
        "occurred_until",
        "dependency_hash",
        "quiet_until",
        "status",
    )

    op.create_table(
        "memory_summaries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.Column("period_from", sa.DateTime(), nullable=True),
        sa.Column("period_until", sa.DateTime(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("observations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dependency_hash", sa.String(), nullable=False),
        sa.Column("derivation_key", sa.String(), nullable=False),
        sa.Column("coverage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("learned_at", sa.DateTime(), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(), nullable=True),
        sa.Column("is_superseded", sa.Boolean(), nullable=False),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "scope_type IN ('entity','topic','relationship','routine','life_area','period')",
            name="ck_memory_summaries_scope_type",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["superseded_by"], ["memory_summaries.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "derivation_key",
            name="uq_memory_summary_derivation",
        ),
    )
    op.create_index(
        "ix_memory_summaries_scope_current",
        "memory_summaries",
        ["owner_user_id", "scope_type", "scope_id", "is_superseded"],
    )
    _create_simple_indexes(
        "memory_summaries",
        "owner_user_id",
        "scope_type",
        "scope_id",
        "period_from",
        "period_until",
        "dependency_hash",
        "derivation_key",
        "is_superseded",
    )


def downgrade() -> None:
    op.drop_table("memory_summaries")
    op.drop_table("dirty_scopes")
    op.drop_table("derivation_attempts")
    op.drop_table("derivation_runs")
    op.drop_table("entity_resolution_decisions")
    op.drop_table("fact_evidence")
    op.drop_table("claim_evidence")
    op.drop_table("memory_claims")
    op.drop_table("entity_mentions")
    op.drop_table("evidence_spans")
    op.drop_table("evidence_documents")


def _create_simple_indexes(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(op.f(f"ix_{table}_{column}"), table, [column], unique=False)

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Column, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class EntityMention(SQLModel, table=True):
    """A grounded entity mention before or after conservative resolution."""

    __tablename__ = "entity_mentions"
    __table_args__ = (
        CheckConstraint(
            "resolution_status IN ('unresolved','resolved','ambiguous','rejected')",
            name="ck_entity_mentions_resolution_status",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_entity_mentions_confidence",
        ),
        UniqueConstraint("owner_user_id", "derivation_key", name="uq_entity_mention_derivation"),
        Index("ix_entity_mentions_owner_name", "owner_user_id", "entity_type", "normalized_text"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    span_id: uuid.UUID = Field(foreign_key="evidence_spans.id", nullable=False, index=True)
    surface_text: str = Field(nullable=False)
    normalized_text: str = Field(nullable=False, index=True)
    entity_type: str = Field(nullable=False, index=True)
    attributes: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    confidence: float | None = None
    extractor: str = Field(nullable=False)
    extraction_version: int = Field(nullable=False)
    ontology_version: str = Field(nullable=False)
    resolution_status: str = Field(default="unresolved", nullable=False, index=True)
    resolved_entity_id: uuid.UUID | None = Field(default=None, foreign_key="entities.id", index=True)
    derivation_key: str = Field(nullable=False, index=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    resolved_at: datetime | None = None


class MemoryClaim(SQLModel, table=True):
    """An immutable, evidence-backed assertion awaiting or recording reconciliation."""

    __tablename__ = "memory_claims"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('relation','attribute','measurement','commitment','classification','temporal')",
            name="ck_memory_claims_kind",
        ),
        CheckConstraint("polarity IN ('positive','negative')", name="ck_memory_claims_polarity"),
        CheckConstraint(
            "modality IN ('asserted','possible','planned','requested','inferred')",
            name="ck_memory_claims_modality",
        ),
        CheckConstraint(
            "reconciliation_status IN ('pending','accepted','corroborating','conflicting',"
            "'superseded','rejected','review')",
            name="ck_memory_claims_reconciliation_status",
        ),
        CheckConstraint(
            "extraction_confidence IS NULL OR "
            "(extraction_confidence >= 0 AND extraction_confidence <= 1)",
            name="ck_memory_claims_extraction_confidence",
        ),
        CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)",
            name="ck_memory_claims_quality_score",
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from",
            name="ck_memory_claims_valid_range",
        ),
        UniqueConstraint("owner_user_id", "derivation_key", name="uq_memory_claim_derivation"),
        Index("ix_memory_claims_owner_predicate", "owner_user_id", "predicate"),
        Index("ix_memory_claims_owner_state", "owner_user_id", "reconciliation_status"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    kind: str = Field(nullable=False, index=True)
    subject_mention_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="entity_mentions.id",
        index=True,
    )
    subject_entity_id: uuid.UUID | None = Field(default=None, foreign_key="entities.id", index=True)
    predicate: str = Field(nullable=False, index=True)
    object_mention_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="entity_mentions.id",
        index=True,
    )
    object_entity_id: uuid.UUID | None = Field(default=None, foreign_key="entities.id", index=True)
    value: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    polarity: str = Field(default="positive", nullable=False)
    modality: str = Field(default="asserted", nullable=False)
    valid_from: datetime | None = Field(default=None, index=True)
    valid_until: datetime | None = Field(default=None, index=True)
    time_precision: str | None = None
    extraction_confidence: float | None = None
    quality_score: float | None = None
    reconciliation_status: str = Field(default="pending", nullable=False, index=True)
    extractor: str = Field(nullable=False)
    extraction_version: int = Field(nullable=False)
    ontology_version: str = Field(nullable=False)
    derivation_key: str = Field(nullable=False, index=True)
    canonical_target_type: str | None = Field(default=None, index=True)
    canonical_target_id: uuid.UUID | None = Field(default=None, index=True)
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    learned_at: datetime = Field(default_factory=_utcnow, nullable=False)
    invalidated_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class ClaimEvidence(SQLModel, table=True):
    """Many-to-many provenance from a claim to exact evidence."""

    __tablename__ = "claim_evidence"
    __table_args__ = (
        CheckConstraint(
            "role IN ('direct','context','contradiction','correction','user_confirmation')",
            name="ck_claim_evidence_role",
        ),
        UniqueConstraint(
            "claim_id",
            "span_id",
            "event_id",
            "source_record_id",
            "role",
            name="uq_claim_evidence_source",
        ),
        Index("ix_claim_evidence_claim", "claim_id", "role"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    claim_id: uuid.UUID = Field(foreign_key="memory_claims.id", nullable=False, index=True)
    span_id: uuid.UUID | None = Field(default=None, foreign_key="evidence_spans.id", index=True)
    event_id: uuid.UUID | None = Field(default=None, foreign_key="events.id", index=True)
    source_record_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="source_records.id",
        index=True,
    )
    role: str = Field(default="direct", nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class FactEvidence(SQLModel, table=True):
    """Links an accepted projection to all claims that currently support it."""

    __tablename__ = "fact_evidence"
    __table_args__ = (
        UniqueConstraint("target_type", "target_id", "claim_id", name="uq_fact_evidence_claim"),
        Index("ix_fact_evidence_target", "target_type", "target_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    target_type: str = Field(nullable=False, index=True)
    target_id: uuid.UUID = Field(nullable=False, index=True)
    claim_id: uuid.UUID = Field(foreign_key="memory_claims.id", nullable=False, index=True)
    role: str = Field(default="support", nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class EntityResolutionDecision(SQLModel, table=True):
    """Explainable candidate decision for one mention and one entity."""

    __tablename__ = "entity_resolution_decisions"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('accepted','rejected','review','superseded')",
            name="ck_entity_resolution_decisions_outcome",
        ),
        CheckConstraint("score >= 0 AND score <= 1", name="ck_entity_resolution_decisions_score"),
        UniqueConstraint("mention_id", "candidate_entity_id", "method", name="uq_resolution_candidate_method"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    mention_id: uuid.UUID = Field(foreign_key="entity_mentions.id", nullable=False, index=True)
    candidate_entity_id: uuid.UUID = Field(foreign_key="entities.id", nullable=False, index=True)
    method: str = Field(nullable=False, index=True)
    score: float = Field(nullable=False)
    components: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    outcome: str = Field(nullable=False, index=True)
    model_role: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    review_item_id: uuid.UUID | None = Field(default=None, foreign_key="review_items.id", index=True)
    explanation: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

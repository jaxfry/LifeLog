import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Column, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class DerivationRun(SQLModel, table=True):
    """Immutable lineage for one versioned derived computation."""

    __tablename__ = "derivation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed','skipped','cancelled')",
            name="ck_derivation_runs_status",
        ),
        UniqueConstraint("owner_user_id", "derivation_key", name="uq_derivation_run_key"),
        Index("ix_derivation_runs_owner_purpose", "owner_user_id", "purpose", "status"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    purpose: str = Field(nullable=False, index=True)
    target_type: str = Field(nullable=False, index=True)
    target_id: uuid.UUID = Field(nullable=False, index=True)
    derivation_key: str = Field(nullable=False, index=True)
    input_fingerprint: str = Field(nullable=False, index=True)
    processor: str = Field(nullable=False)
    processor_version: str = Field(nullable=False)
    prompt_version: str | None = None
    ontology_version: str | None = None
    model_role: str | None = None
    provider: str | None = None
    model: str | None = None
    policy_snapshot: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    budget_snapshot: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    output_refs: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    status: str = Field(default="pending", nullable=False, index=True)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class DerivationAttempt(SQLModel, table=True):
    """Append-only attempt history for a derivation run."""

    __tablename__ = "derivation_attempts"
    __table_args__ = (
        UniqueConstraint("derivation_run_id", "attempt", name="uq_derivation_attempt_number"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    derivation_run_id: uuid.UUID = Field(
        foreign_key="derivation_runs.id",
        nullable=False,
        index=True,
    )
    attempt: int = Field(nullable=False)
    status: str = Field(nullable=False, index=True)
    error_type: str | None = None
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    started_at: datetime = Field(default_factory=_utcnow, nullable=False)
    completed_at: datetime | None = None


class DirtyScope(SQLModel, table=True):
    """A coalescible bounded request for deterministic reconciliation."""

    __tablename__ = "dirty_scopes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','queued','running','resolved','cancelled')",
            name="ck_dirty_scopes_status",
        ),
        CheckConstraint(
            "materiality >= 0 AND materiality <= 1",
            name="ck_dirty_scopes_materiality",
        ),
        CheckConstraint(
            "occurred_until IS NULL OR occurred_from IS NULL OR occurred_until >= occurred_from",
            name="ck_dirty_scopes_time_range",
        ),
        Index("ix_dirty_scopes_owner_status", "owner_user_id", "status", "quiet_until"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    reason: str = Field(nullable=False, index=True)
    occurred_from: datetime | None = Field(default=None, index=True)
    occurred_until: datetime | None = Field(default=None, index=True)
    entity_ids: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    source_refs: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    dependency_hash: str = Field(nullable=False, index=True)
    materiality: float = Field(default=0.0, nullable=False)
    quiet_until: datetime | None = Field(default=None, index=True)
    status: str = Field(default="pending", nullable=False, index=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class MemorySummary(SQLModel, table=True):
    """A versioned, evidence-backed longitudinal consolidation projection."""

    __tablename__ = "memory_summaries"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('entity','topic','relationship','routine','life_area','period')",
            name="ck_memory_summaries_scope_type",
        ),
        UniqueConstraint("owner_user_id", "derivation_key", name="uq_memory_summary_derivation"),
        Index("ix_memory_summaries_scope_current", "owner_user_id", "scope_type", "scope_id", "is_superseded"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    scope_type: str = Field(nullable=False, index=True)
    scope_id: uuid.UUID | None = Field(default=None, index=True)
    period_from: datetime | None = Field(default=None, index=True)
    period_until: datetime | None = Field(default=None, index=True)
    summary_text: str = Field(sa_column=Column(Text, nullable=False))
    observations: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    dependency_hash: str = Field(nullable=False, index=True)
    derivation_key: str = Field(nullable=False, index=True)
    coverage: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    learned_at: datetime = Field(default_factory=_utcnow, nullable=False)
    invalidated_at: datetime | None = None
    is_superseded: bool = Field(default=False, nullable=False, index=True)
    superseded_by: uuid.UUID | None = Field(default=None, foreign_key="memory_summaries.id")
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

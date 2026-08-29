from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class FileAttachment(SQLModel, table=True):
    __tablename__ = "file_attachments"
    __table_args__ = (
        CheckConstraint(
            "processing_status IN ('pending','processing','ready','failed')",
            name="ck_file_attachments_processing_status",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_user_id: UUID | None = Field(default=None, foreign_key="users.id", index=True)

    filename: str = Field(nullable=False)
    stored_path: str = Field(nullable=False)
    mime_type: str = Field(nullable=False)
    size_bytes: int = Field(default=0)
    content_hash: str = Field(index=True, nullable=False)

    event_id: UUID | None = Field(default=None, foreign_key="events.id", index=True)
    timeline_id: UUID | None = Field(default=None, foreign_key="timeline_entries.id", index=True)

    category: str | None = Field(default=None, index=True)
    tags: list[str] = Field(default=[], sa_column=Column(JSONB))

    description: str | None = None
    ai_metadata: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    user_metadata: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    technical_metadata: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))

    is_processed: bool = Field(default=False)
    processing_status: str = Field(default="pending", index=True)
    processing_version: int = Field(default=1)
    processing_error: str | None = None
    source_extension_id: str | None = Field(default=None, foreign_key="extensions.id", index=True)
    processed_at: datetime | None = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None)
    )


class ContentChunk(SQLModel, table=True):
    """Searchable, cited content derived from an immutable attachment."""

    __tablename__ = "content_chunks"
    __table_args__ = (
        UniqueConstraint("file_id", "processing_version", "sequence", name="uq_content_chunk_version_sequence"),
        CheckConstraint("sequence >= 0", name="ck_content_chunks_sequence"),
        CheckConstraint("processing_version >= 1", name="ck_content_chunks_processing_version"),
        Index("ix_content_chunks_file_current", "file_id", "is_superseded"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    file_id: UUID = Field(foreign_key="file_attachments.id", nullable=False, index=True)
    sequence: int = Field(nullable=False)
    content: str = Field(sa_column=Column(Text, nullable=False))
    content_type: str = Field(nullable=False, index=True)
    locator: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    processing_version: int = Field(default=1, nullable=False)
    is_superseded: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class MemoryProposal(SQLModel, table=True):
    """Auditable AI suggestion awaiting or recording deterministic promotion."""

    __tablename__ = "memory_proposals"
    __table_args__ = (
        CheckConstraint("kind IN ('entity','relation','commitment')", name="ck_memory_proposals_kind"),
        CheckConstraint("status IN ('pending','accepted','rejected')", name="ck_memory_proposals_status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_proposals_confidence"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    file_id: UUID = Field(foreign_key="file_attachments.id", nullable=False, index=True)
    chunk_id: UUID = Field(foreign_key="content_chunks.id", nullable=False, index=True)
    kind: str = Field(nullable=False, index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    evidence_quote: str = Field(sa_column=Column(Text, nullable=False))
    confidence: float = Field(nullable=False)
    status: str = Field(default="pending", nullable=False, index=True)
    extractor: str = Field(nullable=False)
    extraction_version: int = Field(default=1, nullable=False)
    promoted_id: UUID | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    decided_at: datetime | None = None


class Commitment(SQLModel, table=True):
    """Generic actionable obligation inferred from or added to LifeLog."""

    __tablename__ = "commitments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('suggested','planned','in_progress','completed','cancelled')",
            name="ck_commitments_status",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_commitments_confidence",
        ),
        CheckConstraint("due_at IS NULL OR not_before IS NULL OR due_at >= not_before", name="ck_commitments_window"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_user_id: UUID | None = Field(default=None, foreign_key="users.id", index=True)
    title: str = Field(nullable=False, index=True)
    description: str | None = None
    status: str = Field(default="suggested", nullable=False, index=True)
    due_at: datetime | None = Field(default=None, index=True)
    not_before: datetime | None = None
    completed_at: datetime | None = None
    confidence: float | None = None
    source_file_id: UUID | None = Field(default=None, foreign_key="file_attachments.id", index=True)
    source_chunk_id: UUID | None = Field(default=None, foreign_key="content_chunks.id")
    source_event_id: UUID | None = Field(default=None, foreign_key="events.id")
    source_record_id: UUID | None = Field(default=None, foreign_key="source_records.id", index=True)
    mapping_key: str | None = Field(default=None, index=True)
    superseded_by: UUID | None = Field(default=None, foreign_key="commitments.id", index=True)
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class Notification(SQLModel, table=True):
    """Durable core notification/outbox record; delivery channels are adapters."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','delivered','dismissed','cancelled','failed')",
            name="ck_notifications_status",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_user_id: UUID | None = Field(default=None, foreign_key="users.id", index=True)
    commitment_id: UUID | None = Field(default=None, foreign_key="commitments.id", index=True)
    channel: str = Field(default="in_app", nullable=False)
    title: str = Field(nullable=False)
    body: str | None = None
    scheduled_for: datetime = Field(nullable=False, index=True)
    status: str = Field(default="pending", nullable=False, index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    attempts: int = Field(default=0)
    delivered_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class CommitmentProgress(SQLModel, table=True):
    """Evidence that work advanced, independent of any one life domain."""

    __tablename__ = "commitment_progress"
    __table_args__ = (
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_progress_confidence"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_user_id: UUID | None = Field(default=None, foreign_key="users.id", index=True)
    commitment_id: UUID = Field(foreign_key="commitments.id", nullable=False, index=True)
    event_id: UUID | None = Field(default=None, foreign_key="events.id", index=True)
    amount: float = Field(default=1.0)
    unit: str = Field(default="observation", nullable=False)
    note: str | None = None
    confidence: float | None = None
    observed_at: datetime = Field(nullable=False, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


class PlanBlock(SQLModel, table=True):
    """A revisable allocation of time toward a generic commitment."""

    __tablename__ = "plan_blocks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('suggested','accepted','completed','skipped','cancelled')",
            name="ck_plan_blocks_status",
        ),
        CheckConstraint("end_at > start_at", name="ck_plan_blocks_window"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_user_id: UUID | None = Field(default=None, foreign_key="users.id", index=True)
    commitment_id: UUID = Field(foreign_key="commitments.id", nullable=False, index=True)
    start_at: datetime = Field(nullable=False, index=True)
    end_at: datetime = Field(nullable=False, index=True)
    status: str = Field(default="suggested", nullable=False, index=True)
    rationale: str | None = None
    planner_version: int = Field(default=1, nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))

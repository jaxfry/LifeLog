import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Column, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class EvidenceDocument(SQLModel, table=True):
    """A versioned, LifeLog-owned representation of immutable source evidence."""

    __tablename__ = "evidence_documents"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('document','image','transcript','note','event','structured')",
            name="ck_evidence_documents_kind",
        ),
        UniqueConstraint("owner_user_id", "derivation_key", name="uq_evidence_document_derivation"),
        Index("ix_evidence_documents_file_current", "source_file_id", "is_superseded"),
        Index("ix_evidence_documents_capture_current", "capture_id", "is_superseded"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    source_file_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="file_attachments.id",
        index=True,
    )
    capture_id: uuid.UUID | None = Field(default=None, foreign_key="captures.id", index=True)
    source_event_id: uuid.UUID | None = Field(default=None, foreign_key="events.id", index=True)
    kind: str = Field(nullable=False, index=True)
    full_text: str = Field(sa_column=Column(Text, nullable=False))
    structure: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    language: str | None = Field(default=None, index=True)
    source_content_hash: str = Field(nullable=False, index=True)
    parser: str = Field(nullable=False)
    parser_version: str = Field(nullable=False)
    derivation_key: str = Field(nullable=False, index=True)
    is_superseded: bool = Field(default=False, nullable=False, index=True)
    superseded_by: uuid.UUID | None = Field(
        default=None,
        foreign_key="evidence_documents.id",
        index=True,
    )
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class EvidenceSpan(SQLModel, table=True):
    """An exact citable range within an evidence document."""

    __tablename__ = "evidence_spans"
    __table_args__ = (
        UniqueConstraint("document_id", "sequence", name="uq_evidence_span_sequence"),
        UniqueConstraint("source_chunk_id", name="uq_evidence_span_source_chunk"),
        CheckConstraint("sequence >= 0", name="ck_evidence_spans_sequence"),
        CheckConstraint(
            "char_start IS NULL OR char_end IS NULL OR char_end >= char_start",
            name="ck_evidence_spans_character_range",
        ),
        CheckConstraint(
            "start_seconds IS NULL OR end_seconds IS NULL OR end_seconds >= start_seconds",
            name="ck_evidence_spans_time_range",
        ),
        Index("ix_evidence_spans_document_range", "document_id", "char_start", "char_end"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    document_id: uuid.UUID = Field(
        foreign_key="evidence_documents.id",
        nullable=False,
        index=True,
    )
    source_chunk_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="content_chunks.id",
        index=True,
    )
    sequence: int = Field(nullable=False)
    text: str = Field(sa_column=Column(Text, nullable=False))
    char_start: int | None = None
    char_end: int | None = None
    page_number: int | None = Field(default=None, index=True)
    bounding_box: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    start_seconds: float | None = None
    end_seconds: float | None = None
    speaker_label: str | None = Field(default=None, index=True)
    structural_path: str | None = None
    locator: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    content_hash: str = Field(nullable=False, index=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

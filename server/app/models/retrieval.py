import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class SearchDocument(SQLModel, table=True):
    """Disposable, rebuildable recall projection over durable LifeLog records."""

    __tablename__ = "search_documents"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", "version", name="uq_search_document_source_version"),
        Index("ix_search_documents_current_type", "is_superseded", "source_type"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    source_type: str = Field(nullable=False, index=True)
    source_id: uuid.UUID = Field(nullable=False, index=True)
    version: int = Field(default=1, nullable=False)
    title: str | None = None
    content: str = Field(sa_column=Column(Text, nullable=False))
    occurred_at: datetime | None = Field(default=None, index=True)
    logical_date: str | None = Field(default=None, index=True)
    embedding: list[float] | None = Field(default=None, sa_column=Column(Vector(768), nullable=True))
    embedding_model: str | None = None
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSONB, nullable=False),
    )
    is_superseded: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class ProcessingFailure(SQLModel, table=True):
    """Durable dead-letter record for work that must never vanish into logs."""

    __tablename__ = "processing_failures"
    __table_args__ = (
        Index("ix_processing_failures_open", "status", "stage"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    source_type: str = Field(nullable=False, index=True)
    source_id: uuid.UUID | None = Field(default=None, index=True)
    stage: str = Field(nullable=False, index=True)
    status: str = Field(default="open", nullable=False, index=True)
    attempts: int = Field(default=1, nullable=False)
    error_type: str = Field(nullable=False)
    error_message: str = Field(sa_column=Column(Text, nullable=False))
    traceback: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    context: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    last_failed_at: datetime = Field(default_factory=_utcnow, nullable=False)
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

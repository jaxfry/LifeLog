import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Column, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Entity(SQLModel, table=True):
    __tablename__ = "entities"
    __table_args__ = (
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_entities_confidence"),
        Index(
            "uq_entities_current_canonical_key",
            "entity_type",
            "canonical_key",
            unique=True,
            postgresql_where=text("is_superseded = false AND canonical_key IS NOT NULL"),
            sqlite_where=text("is_superseded = 0 AND canonical_key IS NOT NULL"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entity_type: str = Field(index=True, nullable=False)
    name: str | None = None
    canonical_key: str | None = Field(default=None, index=True)
    data: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    confidence: float | None = None
    is_superseded: bool = Field(default=False, index=True)
    superseded_by: uuid.UUID | None = Field(default=None, foreign_key="entities.id")
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class EntityAlias(SQLModel, table=True):
    __tablename__ = "entity_aliases"
    __table_args__ = (
        UniqueConstraint("entity_id", "canonical_key", name="uq_entity_alias_key"),
        Index("ix_entity_aliases_canonical_key", "canonical_key"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entity_id: uuid.UUID = Field(foreign_key="entities.id", nullable=False, index=True)
    alias: str = Field(nullable=False)
    canonical_key: str = Field(nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class Relation(SQLModel, table=True):
    __tablename__ = "relations"
    __table_args__ = (
        CheckConstraint(
            "subject_type IN ('entity','event')",
            name="ck_relations_subject_type",
        ),
        CheckConstraint(
            "object_type IN ('entity','event')",
            name="ck_relations_object_type",
        ),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_relations_confidence"),
        CheckConstraint(
            "occurred_until IS NULL OR occurred_from IS NULL OR occurred_until >= occurred_from",
            name="ck_relations_occurred_window",
        ),
        Index("ix_relations_subject_predicate", "subject_id", "predicate"),
        Index("ix_relations_object_predicate", "object_id", "predicate"),
        Index("ix_relations_source_event", "source_event_id"),
        Index("ix_relations_source_file", "source_file_id"),
        Index(
            "uq_relations_extracted_fact",
            "source_event_id",
            "subject_id",
            "predicate",
            "object_id",
            "extractor",
            "extraction_version",
            unique=True,
            postgresql_where=text("source_event_id IS NOT NULL"),
            sqlite_where=text("source_event_id IS NOT NULL"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    subject_id: uuid.UUID = Field(index=True, nullable=False)
    subject_type: str = Field(nullable=False)
    predicate: str = Field(nullable=False)
    object_id: uuid.UUID = Field(index=True, nullable=False)
    object_type: str = Field(nullable=False)
    occurred_from: datetime | None = None
    occurred_until: datetime | None = None
    invalidated_at: datetime | None = None
    confidence: float | None = None
    is_superseded: bool = Field(default=False, index=True)
    superseded_by: uuid.UUID | None = Field(default=None, foreign_key="relations.id")
    source_event_id: uuid.UUID | None = Field(default=None, foreign_key="events.id")
    source_file_id: uuid.UUID | None = Field(default=None, foreign_key="file_attachments.id")
    source_chunk_id: uuid.UUID | None = Field(default=None, foreign_key="content_chunks.id")
    extractor: str | None = None
    extraction_version: int | None = None
    data: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

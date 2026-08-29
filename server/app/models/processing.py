import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.ingest import Event


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID | None = Field(default=None, foreign_key="users.id", index=True)
    start_time: datetime = Field(nullable=False)
    end_time: datetime = Field(nullable=False)
    status: str = Field(default="pending")
    kind: str = Field(default="activity", index=True)
    retry_count: int = Field(default=0)
    logical_date: str | None = Field(default=None, index=True)
    processing_status: str = Field(default="ready")
    last_touched_at: datetime = Field(default_factory=_utcnow, nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)

    events: list["Event"] = Relationship(back_populates="session")
    timeline_entries: list["TimelineEntry"] = Relationship(back_populates="session")


class TimelineEntry(SQLModel, table=True):
    __tablename__ = "timeline_entries"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID | None = Field(default=None, foreign_key="users.id", index=True)
    session_id: uuid.UUID | None = Field(
        default=None, foreign_key="sessions.id", index=True
    )
    start_time: datetime = Field(nullable=False)
    end_time: datetime = Field(nullable=False)
    activity: str = Field(nullable=False)
    notes: str | None = None
    category: str | None = Field(default=None, index=True)
    tags: list[str] = Field(default=None, sa_column=Column(JSONB))
    evidence_event_ids: list[str] = Field(default=None, sa_column=Column(JSONB))
    confidence: float | None = None
    inferences: list[str] = Field(default=None, sa_column=Column(JSONB))
    prompt_id: uuid.UUID | None = Field(
        default=None, foreign_key="prompts.id"
    )
    is_summarized: bool = Field(default=False)
    logical_date: str | None = Field(default=None, index=True)
    timezone: str = Field(default="UTC", nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)

    session: Session | None = Relationship(back_populates="timeline_entries")


class DailySummary(SQLModel, table=True):
    __tablename__ = "daily_summaries"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "logical_date", name="uq_daily_summary_owner_date"),
        Index("ix_daily_summaries_owner_date", "owner_user_id", "logical_date"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_user_id: uuid.UUID | None = Field(default=None, foreign_key="users.id", index=True)
    logical_date: str = Field(index=True, nullable=False)
    summary_text: str = Field(nullable=False)
    key_activities: list[str] = Field(default=None, sa_column=Column(JSONB))
    productivity_score: int | None = None
    mood: str | None = None
    open_loops: list[str] = Field(default=None, sa_column=Column(JSONB))
    inferences: list[str] = Field(default=None, sa_column=Column(JSONB))
    status: str = Field(default="ready")
    last_touched_at: datetime = Field(default_factory=_utcnow, nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)

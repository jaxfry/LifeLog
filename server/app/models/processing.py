import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    start_time: datetime = Field(nullable=False)
    end_time: datetime = Field(nullable=False)
    status: str = Field(default="pending")
    retry_count: int = Field(default=0)
    logical_date: Optional[str] = Field(default=None, index=True)
    processing_status: str = Field(default="ready")
    last_touched_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    events: List["Event"] = Relationship(back_populates="session")
    timeline_entries: List["TimelineEntry"] = Relationship(back_populates="session")


class TimelineEntry(SQLModel, table=True):
    __tablename__ = "timeline_entries"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="sessions.id", index=True
    )
    start_time: datetime = Field(nullable=False)
    end_time: datetime = Field(nullable=False)
    activity: str = Field(nullable=False)
    notes: Optional[str] = None
    category: Optional[str] = Field(default=None, index=True)
    tags: List[str] = Field(
        default=None, sa_column=Column(JSONB)
    )
    prompt_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="prompts.id"
    )
    is_summarized: bool = Field(default=False)
    logical_date: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    session: Optional[Session] = Relationship(back_populates="timeline_entries")


class DailySummary(SQLModel, table=True):
    __tablename__ = "daily_summaries"

    logical_date: str = Field(primary_key=True)
    summary_text: str = Field(nullable=False)
    key_activities: List[str] = Field(
        default=None, sa_column=Column(JSONB)
    )
    productivity_score: Optional[int] = None
    mood: Optional[str] = None
    status: str = Field(default="ready")
    last_touched_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

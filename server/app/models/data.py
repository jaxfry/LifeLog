from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone
from uuid import UUID, uuid4
from enum import Enum as PyEnum
from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy.dialects.postgresql import JSONB

class SessionStatus(str, PyEnum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    SYNTHESIZED = "SYNTHESIZED"
    FAILED = "FAILED"
    DIRTY = "DIRTY"

class RawLog(SQLModel, table=True):
    __tablename__ = "raw_logs"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    device_id: str = Field(index=True)
    extension_id: str = Field(index=True)
    payload: Union[Dict[str, Any], List[Dict[str, Any]]] = Field(sa_column=Column(JSONB))
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    client_timestamp: Optional[datetime] = Field(default=None)
    client_timezone: Optional[str] = Field(default=None) # e.g. "-0500"
    payload_hash: str = Field(index=True, unique=True) # Enforces idempotency

class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    start_time: datetime
    end_time: datetime
    narrative: Optional[str] = Field(default=None)
    refined_summary: Optional[str] = Field(default=None)
    status: SessionStatus = Field(default=SessionStatus.PENDING)
    retry_count: int = Field(default=0)
    
    # Relationships
    events: List["Event"] = Relationship(back_populates="session")
    timeline_entries: List["Timeline"] = Relationship(back_populates="session")

class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    source_log_id: UUID = Field(foreign_key="raw_logs.id")
    session_id: Optional[UUID] = Field(default=None, foreign_key="sessions.id", index=True)
    type: str = Field(index=True)
    data: Dict[str, Any] = Field(sa_column=Column(JSONB))
    processing_version: int = Field(default=1)
    is_superseded: bool = Field(default=False)
    timezone: str = Field(default="UTC")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    session: Optional[Session] = Relationship(back_populates="events")

class Timeline(SQLModel, table=True):
    __tablename__ = "timeline"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: Optional[UUID] = Field(default=None, foreign_key="sessions.id", index=True)
    start_time: datetime
    end_time: datetime
    activity: str
    notes: Optional[str] = None
    timezone: str = Field(default="UTC")
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    session: Optional[Session] = Relationship(back_populates="timeline_entries")

class DailySummary(SQLModel, table=True):
    __tablename__ = "daily_summaries"

    date: datetime = Field(primary_key=True) # YYYY-MM-DD (stored as datetime at midnight UTC)
    summary_text: str
    key_activities: List[str] = Field(sa_column=Column(JSONB))
    productivity_score: Optional[int] = None
    mood: Optional[str] = None
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

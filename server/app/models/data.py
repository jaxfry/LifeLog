from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone
from uuid import UUID, uuid4
from enum import Enum as PyEnum
from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector

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
    client_timezone: Optional[str] = Field(default=None) # Optional offset
    iana_timezone: Optional[str] = Field(default=None) # e.g. "America/New_York"
    logical_date: Optional[str] = Field(default=None, index=True) # YYYY-MM-DD representing the human day
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
    timezone: str = Field(default="UTC") # Keep for backwards compat or as primary
    iana_timezone: Optional[str] = Field(default=None) # Real timezone 
    logical_date: Optional[str] = Field(default=None, index=True) # YYYY-MM-DD
    processing_status: str = Field(default="ready")  # ready, processing, error
    last_touched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    
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
    iana_timezone: Optional[str] = Field(default=None)
    logical_date: Optional[str] = Field(default=None, index=True)
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
    iana_timezone: Optional[str] = Field(default=None)
    logical_date: Optional[str] = Field(default=None, index=True)
    
    # Classification & Vectorization
    tags: List[str] = Field(default=[], sa_column=Column(JSONB))
    category: Optional[str] = Field(default=None, index=True)
    entities: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    embedding: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))
    embedding_model: Optional[str] = Field(default=None)  # e.g., "gemini/text-embedding-004"
    embedding_version: Optional[str] = Field(default=None)  # e.g., "1.0"
    is_summarized: bool = Field(default=False)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    session: Optional[Session] = Relationship(back_populates="timeline_entries")

class DailySummary(SQLModel, table=True):
    __tablename__ = "daily_summaries"

    date: datetime = Field(primary_key=True) # YYYY-MM-DD (stored as datetime at midnight UTC)
    logical_date: str = Field(index=True, default="") # The new true primary identifier
    summary_text: str
    key_activities: List[str] = Field(sa_column=Column(JSONB))
    productivity_score: Optional[int] = None
    mood: Optional[str] = None
    status: str = Field(default="READY") # READY, DIRTY
    last_touched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class DailyChapter(SQLModel, table=True):
    __tablename__ = "daily_chapters"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    date: datetime = Field(index=True) # Legacy
    logical_date: str = Field(index=True, default="")
    start_time: datetime
    end_time: datetime
    title: str
    summary: Optional[str] = None
    
    # Classification & Vectorization
    tags: List[str] = Field(default=[], sa_column=Column(JSONB))
    category: Optional[str] = Field(default=None, index=True)
    embedding: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))
    embedding_model: Optional[str] = Field(default=None)
    embedding_version: Optional[str] = Field(default=None)
    processing_status: str = Field(default="ready")  # ready, processing, error, dirty
    last_touched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

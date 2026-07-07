import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.processing import Session


class RawLog(SQLModel, table=True):
    __tablename__ = "raw_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    device_id: str = Field(index=True, nullable=False)
    extension_id: str = Field(index=True, nullable=False)
    payload: Dict[str, Any] = Field(
        default=None, sa_column=Column(JSONB)
    )
    client_timestamp: Optional[datetime] = None
    client_timezone: Optional[str] = None
    logical_date: Optional[str] = Field(default=None, index=True)
    payload_hash: str = Field(index=True, unique=True, nullable=False)
    received_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    processing_status: str = Field(default="pending")


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    source_log_id: uuid.UUID = Field(
        foreign_key="raw_logs.id", nullable=False, index=True
    )
    session_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="sessions.id", index=True
    )
    event_type: str = Field(index=True, nullable=False)
    start_time: datetime = Field(nullable=False)
    end_time: Optional[datetime] = None
    data: Dict[str, Any] = Field(
        default=None, sa_column=Column(JSONB)
    )
    processing_version: int = Field(default=1)
    is_superseded: bool = Field(default=False)
    logical_date: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    session: Optional["Session"] = Relationship(back_populates="events")

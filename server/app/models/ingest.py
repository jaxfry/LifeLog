import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.processing import Session


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class RawLog(SQLModel, table=True):
    __tablename__ = "raw_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    device_id: str = Field(index=True, nullable=False)
    extension_id: str = Field(index=True, nullable=False)
    payload: dict[str, Any] = Field(default=None, sa_column=Column(JSONB))
    client_timestamp: datetime | None = None
    client_timezone: str | None = None
    logical_date: str | None = Field(default=None, index=True)
    payload_hash: str = Field(index=True, unique=True, nullable=False)
    received_at: datetime = Field(default_factory=_utcnow, nullable=False)
    processing_status: str = Field(default="pending")


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    source_log_id: uuid.UUID = Field(
        foreign_key="raw_logs.id", nullable=False, index=True
    )
    session_id: uuid.UUID | None = Field(
        default=None, foreign_key="sessions.id", index=True
    )
    event_type: str = Field(index=True, nullable=False)
    start_time: datetime = Field(nullable=False)
    end_time: datetime | None = None
    data: dict[str, Any] = Field(default=None, sa_column=Column(JSONB))
    processing_version: int = Field(default=1)
    is_superseded: bool = Field(default=False)
    confidence: float | None = None
    memory_extraction_version: int | None = Field(default=None, index=True)
    superseded_by: uuid.UUID | None = Field(default=None, foreign_key="events.id")
    logical_date: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

    session: Optional["Session"] = Relationship(back_populates="events")

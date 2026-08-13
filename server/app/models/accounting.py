import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AIUsage(SQLModel, table=True):
    __tablename__ = "ai_usage"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    timeline_entry_id: uuid.UUID | None = Field(
        default=None, foreign_key="timeline_entries.id"
    )
    operation: str | None = Field(default=None, index=True)
    source_file_id: uuid.UUID | None = Field(default=None, foreign_key="file_attachments.id", index=True)
    source_event_id: uuid.UUID | None = Field(default=None, foreign_key="events.id", index=True)
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    provider: str = Field(nullable=False)
    model: str = Field(nullable=False)
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    cost: float = Field(default=0.0)
    latency_ms: int = Field(default=0)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class AIUsage(SQLModel, table=True):
    __tablename__ = "ai_usage"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    timeline_entry_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="timeline_entries.id"
    )
    provider: str = Field(nullable=False)
    model: str = Field(nullable=False)
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    cost: float = Field(default=0.0)
    latency_ms: int = Field(default=0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

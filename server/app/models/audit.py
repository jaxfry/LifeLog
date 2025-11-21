from typing import Optional, Dict, Any
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import JSONB

class AIUsage(SQLModel, table=True):
    __tablename__ = "ai_usage"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    timeline_entry_id: Optional[UUID] = Field(default=None, index=True)
    provider: str # e.g., "openai", "anthropic"
    model: str # e.g., "gpt-4"
    input_tokens: int
    output_tokens: int
    cost: float
    latency: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Blob(SQLModel, table=True):
    __tablename__ = "blobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hash: str = Field(index=True, unique=True)
    path: str
    mime_type: str
    size_bytes: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Failure(SQLModel, table=True):
    __tablename__ = "failures"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    traceback: str
    context: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    resolved: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

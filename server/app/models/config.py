from typing import Optional, Dict, Any
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.postgresql import JSONB

class Device(SQLModel, table=True):
    __tablename__ = "devices"

    id: str = Field(primary_key=True) # e.g., "iphone-12-jaxon"
    name: Optional[str] = None
    type: Optional[str] = None
    api_key_hash: str
    last_cursor: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class Extension(SQLModel, table=True):
    __tablename__ = "extensions"

    id: str = Field(primary_key=True) # e.g., "com.lifelog.gps"
    version: str
    config: Dict[str, Any] = Field(default={}, sa_column=Column(JSONB)) # Encrypted in practice, simplified here
    scheduler_cron: Optional[str] = None
    is_active: bool = Field(default=True)

class Prompt(SQLModel, table=True):
    __tablename__ = "prompts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str # e.g., "system_prompt", "daily_summary"
    template: str
    version: int
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class SystemConfig(SQLModel, table=True):
    __tablename__ = "system_config"

    key: str = Field(primary_key=True)
    value: str
    description: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

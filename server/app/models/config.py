import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Extension(SQLModel, table=True):
    __tablename__ = "extensions"

    id: str = Field(primary_key=True)
    version: str = Field(nullable=False)
    api_version: str = Field(default="1", nullable=False)
    config: dict[str, Any] = Field(default={}, sa_column=Column(JSONB))
    scheduler_cron: str | None = None
    is_active: bool = Field(default=True)
    archived_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class SystemConfig(SQLModel, table=True):
    __tablename__ = "system_config"

    key: str = Field(primary_key=True)
    value: str = Field(nullable=False)
    description: str | None = None
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class Prompt(SQLModel, table=True):
    __tablename__ = "prompts"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True, nullable=False)
    template: str = Field(nullable=False)
    version: int = Field(default=1)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)

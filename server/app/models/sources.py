import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Column, Index, LargeBinary, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class SourceConnection(SQLModel, table=True):
    """A user's configured instance of an installed source adapter."""

    __tablename__ = "source_connections"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','paused','error','disconnected')",
            name="ck_source_connections_status",
        ),
        Index("ix_source_connections_extension_active", "extension_id", "is_active"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    extension_id: str = Field(foreign_key="extensions.id", nullable=False, index=True)
    name: str = Field(nullable=False)
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    schedule_cron: str | None = None
    status: str = Field(default="active", nullable=False, index=True)
    is_active: bool = Field(default=True, nullable=False, index=True)
    last_sync_started_at: datetime | None = None
    last_sync_completed_at: datetime | None = None
    last_sync_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class SourceSecret(SQLModel, table=True):
    """Encrypted connection credential; plaintext is never serialized or logged."""

    __tablename__ = "source_secrets"
    __table_args__ = (
        UniqueConstraint("connection_id", "key", name="uq_source_secret_connection_key"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    connection_id: uuid.UUID = Field(
        foreign_key="source_connections.id",
        nullable=False,
        index=True,
    )
    key: str = Field(nullable=False)
    ciphertext: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    key_version: int = Field(default=1, nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class SourceCheckpoint(SQLModel, table=True):
    """Durable acquisition cursor, advanced only after ingestion succeeds."""

    __tablename__ = "source_checkpoints"
    __table_args__ = (
        UniqueConstraint("connection_id", "stream", name="uq_source_checkpoint_stream"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    connection_id: uuid.UUID = Field(
        foreign_key="source_connections.id",
        nullable=False,
        index=True,
    )
    stream: str = Field(default="default", nullable=False)
    value: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    version: int = Field(default=1, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class SourceRecord(SQLModel, table=True):
    """Stable external identity pointing at the latest immutable RawLog revision."""

    __tablename__ = "source_records"
    __table_args__ = (
        UniqueConstraint("connection_id", "external_key", name="uq_source_record_external_key"),
        CheckConstraint(
            "update_policy IN ('append','replace','snapshot')",
            name="ck_source_records_update_policy",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    connection_id: uuid.UUID = Field(
        foreign_key="source_connections.id",
        nullable=False,
        index=True,
    )
    external_key: str = Field(nullable=False)
    current_raw_log_id: uuid.UUID | None = Field(default=None, index=True)
    current_revision: str | None = None
    source_updated_at: datetime | None = None
    update_policy: str = Field(default="replace", nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)

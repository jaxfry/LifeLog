import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Column, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Capture(SQLModel, table=True):
    """The user's durable capture action, before progressive interpretation."""

    __tablename__ = "captures"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('photo','audio','video','note','file','scan')",
            name="ck_captures_kind",
        ),
        CheckConstraint(
            "status IN ('received','preserved','processing','awaiting_review',"
            "'ready','partially_ready','failed','cancelled')",
            name="ck_captures_status",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_capture_user_idempotency"),
        Index("ix_captures_user_created", "user_id", "created_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID | None = Field(default=None, foreign_key="users.id", index=True)
    device_id: str | None = Field(default=None, foreign_key="devices.id", index=True)
    source_connection_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="source_connections.id",
        index=True,
    )
    idempotency_key: str | None = Field(default=None, index=True)
    kind: str = Field(nullable=False, index=True)
    captured_at: datetime = Field(nullable=False, index=True)
    timezone: str | None = None
    intent: str | None = Field(default=None, index=True)
    text_content: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    context_hints: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    privacy: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    classification: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    status: str = Field(default="received", nullable=False, index=True)
    processing_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class CaptureArtifact(SQLModel, table=True):
    __tablename__ = "capture_artifacts"
    __table_args__ = (
        UniqueConstraint("capture_id", "file_id", name="uq_capture_artifact_file"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    capture_id: uuid.UUID = Field(foreign_key="captures.id", nullable=False, index=True)
    file_id: uuid.UUID = Field(foreign_key="file_attachments.id", nullable=False, index=True)
    role: str = Field(default="original", nullable=False)
    sequence: int = Field(default=0, nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class UploadSession(SQLModel, table=True):
    """Recoverable upload state for large/offline media."""

    __tablename__ = "upload_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','uploading','complete','cancelled','expired','failed')",
            name="ck_upload_sessions_status",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    capture_id: uuid.UUID = Field(foreign_key="captures.id", nullable=False, index=True)
    filename: str = Field(nullable=False)
    mime_type: str = Field(nullable=False)
    total_bytes: int = Field(nullable=False)
    received_bytes: int = Field(default=0, nullable=False)
    temp_path: str = Field(nullable=False)
    status: str = Field(default="pending", nullable=False, index=True)
    content_hash: str | None = None
    expires_at: datetime = Field(nullable=False, index=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class ProcessingJob(SQLModel, table=True):
    """Versioned, stage-level progress for all derived processing."""

    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed','skipped','cancelled')",
            name="ck_processing_jobs_status",
        ),
        UniqueConstraint(
            "target_type",
            "target_id",
            "stage",
            "input_version",
            name="uq_processing_job_stage_version",
        ),
        Index("ix_processing_jobs_target_status", "target_type", "target_id", "status"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    capture_id: uuid.UUID | None = Field(default=None, foreign_key="captures.id", index=True)
    target_type: str = Field(nullable=False, index=True)
    target_id: uuid.UUID = Field(nullable=False, index=True)
    stage: str = Field(nullable=False, index=True)
    status: str = Field(default="pending", nullable=False, index=True)
    input_version: int = Field(default=1, nullable=False)
    processor: str = Field(nullable=False)
    processor_version: str = Field(default="1", nullable=False)
    attempts: int = Field(default=0, nullable=False)
    output_refs: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    error_type: str | None = None
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)

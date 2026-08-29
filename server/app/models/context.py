import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Column, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class LifeArea(SQLModel, table=True):
    """A user-owned lens over shared memory, never a separate memory store."""

    __tablename__ = "life_areas"
    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_life_area_user_slug"),
        Index("ix_life_areas_user_active", "user_id", "is_active"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    slug: str = Field(nullable=False, index=True)
    name: str = Field(nullable=False)
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    icon: str | None = None
    color: str | None = None
    definition: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    is_active: bool = Field(default=True, nullable=False, index=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class ContextLink(SQLModel, table=True):
    """Many-to-many relevance between one memory target and a Life Area."""

    __tablename__ = "context_links"
    __table_args__ = (
        UniqueConstraint("life_area_id", "target_type", "target_id", name="uq_context_link_target"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_context_links_confidence"),
        Index("ix_context_links_target", "target_type", "target_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    life_area_id: uuid.UUID = Field(foreign_key="life_areas.id", nullable=False, index=True)
    target_type: str = Field(nullable=False, index=True)
    target_id: uuid.UUID = Field(nullable=False, index=True)
    role: str = Field(default="relevant", nullable=False)
    source: str = Field(default="user", nullable=False)
    confidence: float = Field(default=1.0, nullable=False)
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class MemoryPolicy(SQLModel, table=True):
    """Purpose-aware disclosure policy attached to a durable or derived target."""

    __tablename__ = "memory_policies"
    __table_args__ = (
        UniqueConstraint("user_id", "target_type", "target_id", name="uq_memory_policy_target"),
        CheckConstraint(
            "visibility IN ('global','selected_areas','private')",
            name="ck_memory_policies_visibility",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    target_type: str = Field(nullable=False, index=True)
    target_id: uuid.UUID = Field(nullable=False, index=True)
    visibility: str = Field(default="global", nullable=False, index=True)
    allowed_area_ids: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    sensitivity: str | None = Field(default=None, index=True)
    reason: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class ReviewItem(SQLModel, table=True):
    """One quiet user Inbox over heterogeneous correction workflows."""

    __tablename__ = "review_items"
    __table_args__ = (
        UniqueConstraint("user_id", "source_type", "source_id", name="uq_review_item_source"),
        CheckConstraint(
            "status IN ('pending','accepted','rejected','dismissed')",
            name="ck_review_items_status",
        ),
        CheckConstraint(
            "priority IN ('low','normal','high')",
            name="ck_review_items_priority",
        ),
        Index("ix_review_items_user_status", "user_id", "status"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    kind: str = Field(nullable=False, index=True)
    source_type: str = Field(nullable=False, index=True)
    source_id: uuid.UUID = Field(nullable=False, index=True)
    capture_id: uuid.UUID | None = Field(default=None, foreign_key="captures.id", index=True)
    life_area_id: uuid.UUID | None = Field(default=None, foreign_key="life_areas.id", index=True)
    title: str = Field(nullable=False)
    summary: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    choices: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    consequential: bool = Field(default=False, nullable=False, index=True)
    confidence: float | None = None
    priority: str = Field(default="normal", nullable=False, index=True)
    expires_at: datetime | None = None
    status: str = Field(default="pending", nullable=False, index=True)
    decided_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class ReviewDecision(SQLModel, table=True):
    """Immutable resolution history for one review item."""

    __tablename__ = "review_decisions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    review_item_id: uuid.UUID = Field(foreign_key="review_items.id", nullable=False, index=True)
    decision: str = Field(nullable=False)
    value: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    decided_at: datetime = Field(default_factory=_utcnow, nullable=False)

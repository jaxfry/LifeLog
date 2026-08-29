import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def stable_revision(payload: dict[str, Any]) -> str:
    """Return a deterministic content revision for sources without native revisions."""
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class PollContext(BaseModel):
    """Typed view of the ephemeral runtime object passed to `poll()`."""

    model_config = ConfigDict(extra="forbid")

    connection_id: str
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict, repr=False)
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    checkpoints: dict[str, dict[str, Any]] = Field(default_factory=dict)

    def require_secret(self, key: str) -> str:
        value = self.secrets.get(key)
        if not value:
            raise ValueError(f"Missing required source secret: {key}")
        return value

    def checkpoint_for(self, stream: str = "default") -> dict[str, Any]:
        return self.checkpoint if stream == "default" else self.checkpoints.get(stream, {})


class SourceRecord(BaseModel):
    """One source-specific revision; LifeLog owns everything after this boundary."""

    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any]
    external_key: str | None = Field(default=None, max_length=500)
    external_revision: str | None = Field(default=None, max_length=500)
    source_updated_at: datetime | None = None
    update_policy: Literal["append", "replace", "snapshot"] = "append"
    client_timestamp: datetime | None = None
    client_timezone: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.update_policy != "append" and not self.external_key:
            raise ValueError("replace/snapshot records require external_key")

    @classmethod
    def replace(
        cls,
        external_key: str,
        payload: dict[str, Any],
        *,
        revision: str | None = None,
        source_updated_at: datetime | None = None,
    ) -> "SourceRecord":
        return cls(
            payload=payload,
            external_key=external_key,
            external_revision=revision or stable_revision(payload),
            source_updated_at=source_updated_at,
            update_policy="replace",
        )


class PollPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[SourceRecord] = Field(default_factory=list)
    next_checkpoint: dict[str, Any] | None = None
    checkpoint_stream: str = Field(default="default", pattern=r"^[A-Za-z0-9_.-]{1,100}$")
    has_more: bool = False

    def model_post_init(self, __context: Any) -> None:
        if self.has_more and self.next_checkpoint is None:
            raise ValueError("has_more requires next_checkpoint")


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1, max_length=200)
    data: dict[str, Any]


class EntityMapping(BaseModel):
    """Resolve a stable entity from normalized event fields."""

    model_config = ConfigDict(extra="forbid")

    event_type: str
    entity_ref: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    entity_type: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name_path: str = Field(min_length=1)
    identity_path: str | None = Field(
        default=None,
        description="Dot path to an external stable identity, stored for future resolution",
    )
    aliases_path: str | None = Field(
        default=None,
        description="Dot path to a list of alternate names",
    )
    metadata_paths: dict[str, str] = Field(
        default_factory=dict,
        description="Entity data keys mapped to dot paths rooted at Event.data",
    )
    confidence: float = Field(default=1.0, ge=0, le=1)


class RelationMapping(BaseModel):
    """One deterministic relation; subjects and objects may be the record or a mapped entity."""

    model_config = ConfigDict(extra="forbid")

    event_type: str
    subject: Literal["record", "entity"] = "record"
    subject_entity_ref: str | None = None
    predicate: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    object: Literal["record", "entity"] = "entity"
    object_entity_ref: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)

    def model_post_init(self, __context: Any) -> None:
        if self.subject == "entity" and not self.subject_entity_ref:
            raise ValueError("entity subjects require subject_entity_ref")
        if self.object == "entity" and not self.object_entity_ref:
            raise ValueError("entity objects require object_entity_ref")


class MeasurementMapping(BaseModel):
    """One numeric or text measurement attached to a mapped entity."""

    model_config = ConfigDict(extra="forbid")

    event_type: str
    entity_ref: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    metric: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    value_path: str = Field(min_length=1)
    value_type: Literal["numeric", "text"] = "numeric"
    unit_path: str | None = None
    occurred_at_path: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)


class LifeAreaDefinition(BaseModel):
    """Declarative user-facing lens contributed as an optional template."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=40)
    recognition_hints: list[str] = Field(default_factory=list)
    vocabulary: dict[str, str] = Field(default_factory=dict)
    cards: list[dict[str, Any]] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    policies: dict[str, Any] = Field(default_factory=dict)

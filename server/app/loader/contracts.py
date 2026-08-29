from datetime import datetime
from typing import Any, Literal

from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel, ConfigDict, Field, field_validator

from lifelog_sdk.contracts import (
    EntityMapping,
    LifeAreaDefinition,
    MeasurementMapping,
    RelationMapping,
)


class FactMapping(BaseModel):
    """Declarative deterministic projection from normalized event data to the kernel."""

    event_type: str
    predicate: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    object_entity_type: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    value_path: str = Field(min_length=1, description="Dot path rooted at Event.data")
    transform: Literal["none", "lowercase", "domain"] = "none"
    confidence: float = Field(default=1.0, ge=0, le=1)


class CommitmentMapping(BaseModel):
    """Deterministic source event fields that represent an actionable obligation."""

    event_type: str
    title_path: str = Field(min_length=1)
    due_at_path: str | None = None
    not_before_path: str | None = None
    description_path: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)


class OntologyEntityTypeDefinition(BaseModel):
    """A compatible extension to the shared ontology, never a private graph."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    aliases: list[str] = Field(default_factory=list)


class OntologyPredicateDefinition(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    subject_types: list[Literal["entity", "event"]] = Field(
        default_factory=lambda: ["entity"]
    )
    object_types: list[Literal["entity", "event"]] = Field(
        default_factory=lambda: ["entity"]
    )
    aliases: list[str] = Field(default_factory=list)


class PollEnvelope(BaseModel):
    """One immutable source revision returned by a connector."""

    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any]
    external_key: str | None = Field(default=None, max_length=500)
    external_revision: str | None = Field(default=None, max_length=500)
    source_updated_at: datetime | None = None
    update_policy: Literal["append", "replace", "snapshot"] = "append"
    client_timestamp: datetime | None = None
    client_timezone: str | None = None

    @field_validator("external_key")
    @classmethod
    def normalize_external_key(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    def model_post_init(self, __context: Any) -> None:
        if self.update_policy != "append" and not self.external_key:
            raise ValueError("replace/snapshot records require external_key")


class PollResult(BaseModel):
    """Acquired revisions plus a checkpoint committed after durable ingestion."""

    model_config = ConfigDict(extra="forbid")

    records: list[PollEnvelope] = Field(default_factory=list)
    next_checkpoint: dict[str, Any] | None = None
    checkpoint_stream: str = Field(default="default", pattern=r"^[A-Za-z0-9_.-]{1,100}$")
    has_more: bool = False

    def model_post_init(self, __context: Any) -> None:
        if self.has_more and self.next_checkpoint is None:
            raise ValueError("has_more requires next_checkpoint")


class ExtensionManifest(BaseModel):
    """Stable boundary between source adapters and the LifeLog base."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(pattern=r"^[a-z0-9]+(?:\.[a-z0-9_-]+)+$", max_length=200)
    version: str = Field(min_length=1, max_length=50)
    api_version: Literal["1", "2"] = "1"
    capabilities: list[
        Literal["collector", "normalizer", "artifact_source", "notification_channel"]
    ] = Field(default_factory=lambda: ["normalizer"])
    permissions: list[Literal["network", "filesystem", "notifications"]] = Field(default_factory=list)
    scheduler_cron: str | None = None
    fact_mappings: list[FactMapping] = Field(default_factory=list)
    entity_mappings: list[EntityMapping] = Field(default_factory=list)
    relation_mappings: list[RelationMapping] = Field(default_factory=list)
    measurement_mappings: list[MeasurementMapping] = Field(default_factory=list)
    commitment_mappings: list[CommitmentMapping] = Field(default_factory=list)
    ontology_entity_types: list[OntologyEntityTypeDefinition] = Field(default_factory=list)
    ontology_predicates: list[OntologyPredicateDefinition] = Field(default_factory=list)
    life_areas: list[LifeAreaDefinition] = Field(default_factory=list)

    @field_validator("scheduler_cron")
    @classmethod
    def validate_scheduler_cron(cls, value: str | None) -> str | None:
        if value:
            CronTrigger.from_crontab(value)
        return value


def validate_extension_manifest(data: dict) -> ExtensionManifest:
    return ExtensionManifest.model_validate(data)

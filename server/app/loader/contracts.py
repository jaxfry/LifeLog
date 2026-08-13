from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FactMapping(BaseModel):
    """Declarative deterministic projection from normalized event data to the kernel."""

    event_type: str
    predicate: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    object_entity_type: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    value_path: str = Field(min_length=1, description="Dot path rooted at Event.data")
    transform: Literal["none", "lowercase", "domain"] = "none"
    confidence: float = Field(default=1.0, ge=0, le=1)


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


def validate_extension_manifest(data: dict) -> ExtensionManifest:
    return ExtensionManifest.model_validate(data)

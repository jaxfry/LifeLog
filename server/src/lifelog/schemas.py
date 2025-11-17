from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from .models import ActorType
from typing import Any

class RawLogIn(BaseModel):
    """The data model for a single raw log entry sent to the /ingest endpoint."""
    source_actor_slug: str = Field(
        ..., 
        description="The slug of the SOURCE actor that generated this log.",
        examples=["activitywatch-collector", "ios-shortcuts-collector"]
    )
    data: dict = Field(
        ...,
        description="The raw, unstructured JSON data from the source."
    )
    external_id: Optional[str] = Field(
        None,
        description="Optional external/source event ID for idempotency (e.g., ActivityWatch event ID)"
    )
    idempotency_key: Optional[str] = Field(
        None,
        description="Optional idempotency key to prevent duplicate processing"
    )

class IngestResponse(BaseModel):
    """The response model after successfully ingesting data."""
    status: str = "success"
    message: str
    raw_log_id: int


class ActorBase(BaseModel):
    slug: str
    actor_type: ActorType
    version: str

class ActorCreate(ActorBase):
    pass

class ActorRead(ActorBase):
    id: int

class ExtensionBase(BaseModel):
    slug: str
    name: str
    version: str

class ExtensionCreate(ExtensionBase):
    actors: list[ActorCreate] = []
    config_schema: Optional[dict] = None
    config: Optional[dict] = None

class ExtensionRead(ExtensionBase):
    id: int
    is_active: bool
    actors: list[ActorRead] = []
    config_schema: Optional[dict] = None
    config: Optional[dict] = None

class ExtensionReadWithActors(ExtensionRead):
    actors: list[ActorRead] = []

class ExtensionConfigUpdate(BaseModel):
    """Schema for updating extension configuration."""
    config: dict = Field(..., description="New configuration values to set or update")

class EventTypeBase(BaseModel):
    slug: str
    description: Optional[str] = None

class EventTypeCreate(EventTypeBase):
    pass

class EventTypeRead(EventTypeBase):
    id: int
    owner_extension_id: int


# Device Management Schemas
class DeviceBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(
        ...,
        description="A unique name for this device",
        examples=["my-iphone", "work-laptop"]
    )
    type: Optional[str] = Field(
        None,
        description="The type of device (e.g., 'ios', 'android', 'desktop')",
        examples=["ios", "android", "desktop", "iot"]
    )
    client_metadata: Optional[dict] = Field(
        None,
        description="Optional metadata about the client (OS version, app version, etc.)"
    )


class DeviceCreate(DeviceBase):
    """Schema for creating a new device"""
    pass


class DeviceRead(DeviceBase):
    """Schema for reading device information (without API key)"""
    id: int
    last_seen: Optional[datetime] = None


class DeviceCreateResponse(DeviceRead):
    """Schema for device creation response (includes API key)"""
    api_key: str = Field(
        ...,
        description="The API key for this device. Store this securely - it won't be shown again."
    )


# Extension Health Schemas
class HealthCheckResult(BaseModel):
    """Schema for health check results"""
    model_config = ConfigDict(from_attributes=True)
    
    extension_slug: str = Field(..., description="Extension slug")
    status: str = Field(..., description="Health status: healthy, degraded, or unhealthy")
    last_check: datetime = Field(..., description="When this health check was performed")
    errors: List[str] = Field(default_factory=list, description="List of error messages")
    warnings: List[str] = Field(default_factory=list, description="List of warning messages")
    details: Optional[dict] = Field(default=None, description="Additional health check details")


class ExtensionHealthSummary(BaseModel):
    """Summary of extension health for all extensions"""
    model_config = ConfigDict(from_attributes=True)
    
    extension_slug: str
    extension_name: str
    extension_version: str
    is_active: bool
    health_status: Optional[str] = Field(None, description="Latest health status")
    last_check: Optional[datetime] = Field(None, description="When last checked")
    has_errors: bool = Field(default=False, description="Whether extension has errors")
    has_warnings: bool = Field(default=False, description="Whether extension has warnings")


# Extension Migration Schemas
class MigrationInfo(BaseModel):
    """Information about an applied migration"""
    model_config = ConfigDict(from_attributes=True)
    
    migration_name: str
    applied_at: datetime
    from_version: Optional[str] = None
    to_version: str
    checksum: Optional[str] = None


class ExtensionMigrationStatus(BaseModel):
    """Migration status for an extension"""
    extension_slug: str
    extension_version: str
    applied_migrations: List[MigrationInfo]
    pending_migrations: List[str] = Field(default_factory=list)
    migration_count: int = Field(description="Total number of applied migrations")



class DeviceUpdate(BaseModel):
    """Schema for updating device information"""
    name: Optional[str] = None
    type: Optional[str] = None
    client_metadata: Optional[dict] = None


class DeviceRotateKeyResponse(BaseModel):
    """Response after rotating a device's API key"""
    status: str = "success"
    message: str
    device_id: int
    new_api_key: str = Field(
        ...,
        description="The new API key for this device. Store this securely!"
    )


class TriggerActorResponse(BaseModel):
    """Response after triggering an actor."""
    message: str
    actor_slug: str
    actor_type: ActorType


# ================= AI Management Schemas =================

class AISettingsRead(BaseModel):
    default_embedding_provider_slug: Optional[str] = None
    default_embedding_model: Optional[str] = None
    default_embedding_dim: Optional[int] = None


class AISettingsUpdate(BaseModel):
    default_embedding_provider_slug: Optional[str] = None
    default_embedding_model: Optional[str] = None
    default_embedding_dim: Optional[int] = None


class AIProviderRead(BaseModel):
    id: int
    name: str
    provider_slug: str
    model_type: str
    provider_type: str
    model_path_or_uri: Optional[str] = None
    is_active: bool
    config: Optional[dict[str, Any]] = None


class AIProviderUpdate(BaseModel):
    name: Optional[str] = None
    model_path_or_uri: Optional[str] = None
    is_active: Optional[bool] = None
    config: Optional[dict[str, Any]] = None
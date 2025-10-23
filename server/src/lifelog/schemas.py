from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from .models import ActorType

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

class ExtensionRead(ExtensionBase):
    id: int
    is_active: bool
    actors: list[ActorRead] = []

class ExtensionReadWithActors(ExtensionRead):
    actors: list[ActorRead] = []

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


class DeviceWithKey(DeviceRead):
    """Schema that includes the API key (only returned on creation)"""
    api_key: str = Field(
        ...,
        description="The API key for this device. Store this securely - it won't be shown again!"
    )


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
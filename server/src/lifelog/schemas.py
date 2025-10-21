from pydantic import BaseModel, Field
from typing import Optional
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
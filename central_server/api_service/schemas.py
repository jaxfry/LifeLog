from pydantic import BaseModel, Field, ConfigDict, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date
import uuid
import json

# Base schemas
class BaseSchema(BaseModel):
    """Base schema for all Pydantic models to inherit from."""
    model_config = ConfigDict(from_attributes=True)

# Token schemas (for single-user authentication)
class Token(BaseSchema):
    """Schema for an authentication token."""
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseSchema):
    """Schema for the data encoded in a token."""
    username: Optional[str] = None

# Project schemas
class ProjectBase(BaseSchema):
    """Base schema for project properties."""
    name: str

class ProjectCreate(ProjectBase):
    """Schema for creating a new project."""
    manual_creation: bool = True

class ProjectUpdate(BaseSchema):
    """Schema for updating an existing project."""
    name: Optional[str] = None

class Project(ProjectBase):
    """Schema for a project as returned by the API."""
    id: uuid.UUID
    embedding: Optional[List[float]] = None
    manual_creation: bool

    @validator("embedding", pre=True)
    def parse_embedding(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # Handle cases where the string is not valid JSON
                # This might involve cleaning the string or raising an error
                # For now, we'll raise a ValueError
                raise ValueError("Invalid string format for embedding")
        return v

# Project Suggestion Schemas
class ProjectSuggestion(BaseSchema):
    """Schema for a project suggestion as returned by the API."""
    id: uuid.UUID
    suggested_name: str
    confidence_score: float
    rationale: Optional[Dict[str, Any]] = None
    status: str
    created_at: datetime

# Timeline Entry schemas
class TimelineEntryBase(BaseSchema):
    """Base schema for timeline entry properties."""
    start_time: datetime
    end_time: datetime
    title: str
    summary: Optional[str] = None
    project_id: Optional[uuid.UUID] = None

class TimelineEntryCreate(TimelineEntryBase):
    """Schema for creating a new timeline entry."""
    pass

class TimelineEntryUpdate(BaseSchema):
    """Schema for updating an existing timeline entry."""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    project_id: Optional[uuid.UUID] = None

class TimelineEntry(TimelineEntryBase):
    """Schema for a timeline entry as returned by the API."""
    id: uuid.UUID
    local_day: date
    project: Optional[Project] = None

# Event schemas
class EventBase(BaseSchema):
    """Base schema for event properties."""
    event_type: str
    source: str
    start_time: datetime
    end_time: Optional[datetime] = None
    details: Optional[Dict[str, Any]] = None

class EventCreate(EventBase):
    """Schema for creating a new event."""
    payload_hash: str

class Event(EventBase):
    """Schema for an event as returned by the API."""
    id: uuid.UUID
    payload_hash: str
    local_day: date

# Digital Activity Data schemas
class DigitalActivityDataBase(BaseSchema):
    """Base schema for digital activity data properties."""
    hostname: str
    app: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None

class DigitalActivityData(DigitalActivityDataBase):
    """Schema for digital activity data as returned by the API."""
    event_id: uuid.UUID

# Ingestion schemas (from the original ingestion service)
class LogEvent(BaseSchema):
    """Schema for a single log event from the ingestion service."""
    timestamp: datetime
    type: str
    data: Dict[str, Any]

class LogPayload(BaseSchema):
    """Schema for a payload of log events from the ingestion service."""
    events: List[LogEvent]
    source_id: str
    sent_at_timestamp_utc: datetime

# Response schemas
class DayStats(BaseSchema):
    """Schema for statistics about a given day."""
    total_events: int
    total_duration_hours: float
    top_project: Optional[str] = None
    active_time_hours: float
    break_time_hours: float

class DailySummary(BaseSchema):
    """Schema for the summary of a given day."""
    date: date
    summary: str
    insights: Optional[List[str]] = None

class DayDataResponse(BaseSchema):
    """Schema for the response containing all data for a given day."""
    date: date
    timeline_entries: List[TimelineEntry]
    stats: DayStats
    summary: Optional[DailySummary] = None

# System schemas
class SystemStatus(BaseSchema):
    """Schema for the system status response."""
    status: str
    version: str
    database_connected: bool
    last_processed_time: Optional[datetime] = None
    events_pending: int
    rabbitmq_connected: bool

# Pagination schemas
class PaginationParams(BaseSchema):
    """Schema for pagination parameters in a request."""
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)

class PaginatedResponse(BaseSchema):
    """Generic schema for a paginated response."""
    items: List[Any]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_previous: bool

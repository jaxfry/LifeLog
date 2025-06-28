from pydantic import BaseModel, Field, ConfigDict, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date
import uuid
import json

# Base schemas
class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

# User schemas
class UserBase(BaseSchema):
    username: str

class UserCreate(UserBase):
    password: str

class UserUpdate(UserBase):
    password: Optional[str] = None

class User(UserBase):
    id: uuid.UUID

class UserInDB(User):
    hashed_password: str

# Token schemas
class Token(BaseSchema):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseSchema):
    username: Optional[str] = None

# Project schemas
class ProjectBase(BaseSchema):
    name: str

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseSchema):
    name: Optional[str] = None

class Project(ProjectBase):
    id: uuid.UUID
    embedding: Optional[List[float]] = None

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

# Timeline Entry schemas
class TimelineEntryBase(BaseSchema):
    start_time: datetime
    end_time: datetime
    title: str
    summary: Optional[str] = None
    project_id: Optional[uuid.UUID] = None

class TimelineEntryCreate(TimelineEntryBase):
    pass

class TimelineEntryUpdate(BaseSchema):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    project_id: Optional[uuid.UUID] = None

class TimelineEntry(TimelineEntryBase):
    id: uuid.UUID
    local_day: date
    project: Optional[Project] = None

# Event schemas
class EventBase(BaseSchema):
    event_type: str
    source: str
    start_time: datetime
    end_time: Optional[datetime] = None
    details: Optional[Dict[str, Any]] = None

class EventCreate(EventBase):
    payload_hash: str
    user_id: Optional[uuid.UUID] = None

class Event(EventBase):
    id: uuid.UUID
    payload_hash: str
    local_day: date
    user_id: Optional[uuid.UUID] = None

# Digital Activity Data schemas
class DigitalActivityDataBase(BaseSchema):
    hostname: str
    app: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None

class DigitalActivityData(DigitalActivityDataBase):
    event_id: uuid.UUID

# Ingestion schemas (from the original ingestion service)
class LogEvent(BaseSchema):
    timestamp: datetime
    type: str
    data: Dict[str, Any]

class LogPayload(BaseSchema):
    events: List[LogEvent]
    source_id: str
    sent_at_timestamp_utc: datetime

# Response schemas
class DayStats(BaseSchema):
    total_events: int
    total_duration_hours: float
    top_project: Optional[str] = None
    active_time_hours: float
    break_time_hours: float

class DailySummary(BaseSchema):
    date: date
    summary: str
    insights: Optional[List[str]] = None

class DayDataResponse(BaseSchema):
    date: date
    timeline_entries: List[TimelineEntry]
    stats: DayStats
    summary: Optional[DailySummary] = None

# System schemas
class SystemStatus(BaseSchema):
    status: str
    version: str
    database_connected: bool
    last_processed_time: Optional[datetime] = None
    events_pending: int
    rabbitmq_connected: bool

# Pagination schemas
class PaginationParams(BaseSchema):
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)

class PaginatedResponse(BaseSchema):
    items: List[Any]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_previous: bool

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, date

# --- Base Models & Common ---
class HTTPError(BaseModel):
    detail: Any # Can be a string or List[ErrorDetail] for validation errors

class ErrorDetail(BaseModel):
    loc: Optional[List[str]] = None # Location of the error (e.g., field name)
    msg: str                    # Error message
    type: str                   # Error type (e.g., 'value_error.missing')

# --- Project ---
class ProjectBase(BaseModel):
    name: str = Field(..., json_schema_extra={'example': "LifeLog Development"}, min_length=1)

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel): # Modified to allow partial updates as per common practice for PUT/PATCH
    name: Optional[str] = Field(None, json_schema_extra={'example': "LifeLog Core Development"}, min_length=1)

class Project(ProjectBase):
    id: UUID
    # embedding: Optional[List[float]] # Handled internally, not directly exposed via basic CRUD

    class Config:
        from_attributes = True # Replaces orm_mode = True in Pydantic v2

# --- Timeline Entry ---
class TimelineEntryBase(BaseModel):
    start_time: datetime
    end_time: datetime
    title: str = Field(..., json_schema_extra={'example': "Working on API design document"}, min_length=1)
    summary: Optional[str] = Field(None, json_schema_extra={'example': "Detailed planning for v1 endpoints and data models."})
    project_id: Optional[UUID] = Field(None)

class TimelineEntryCreate(TimelineEntryBase):
    source_event_ids: Optional[List[UUID]] = Field(None, json_schema_extra={'example': ["a1b2c3d4-e5f6-7890-1234-567890abcdef", "b2c3d4e5-f6a7-8901-2345-67890abcdef0"]})

class TimelineEntryUpdate(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    title: Optional[str] = Field(None, json_schema_extra={'example': "Refining API design"}, min_length=1)
    summary: Optional[str] = Field(None, json_schema_extra={'example': "Added error handling and pagination details."})
    project_id: Optional[UUID] = Field(None)
    source_event_ids: Optional[List[UUID]] = Field(None)

class TimelineEntry(TimelineEntryBase):
    id: UUID
    local_day: date # Changed from datetime to date as per schema.sql and common sense for 'local_day'
    project: Optional[Project] = None # Populated if project_id exists

    class Config:
        from_attributes = True

# --- Event (Raw Data) ---
class EventBase(BaseModel):
    source: str = Field(..., json_schema_extra={'example': "activitywatch_aw-watcher-window"})
    event_type: str # Corresponds to event_kind ENUM ('digital_activity', 'health_metric', etc.)
    start_time: datetime
    end_time: Optional[datetime] = None
    payload: Dict # Generic payload for now, can be a Pydantic union for specific event_types

class Event(EventBase):
    id: UUID
    local_day: date # Changed from datetime to date

    class Config:
        from_attributes = True

# --- Daily Summary ---
class DailySummaryStats(BaseModel):
    total_active_time_min: int
    focus_time_min: int
    number_blocks: int
    top_project: Optional[str] = None
    top_activity: Optional[str] = None

class DailySummary(BaseModel):
    day_summary: str # LLM generated summary
    stats: DailySummaryStats
    version: int # Version of the summary generation logic

class DayDataResponse(BaseModel):
    entries: List[TimelineEntry]
    summary: DailySummary

# --- User (for Auth) ---
class UserBase(BaseModel):
    username: str # As per API design plan

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class User(UserBase):
    id: UUID
    # hashed_password: str # Not directly exposed in API responses for security

    class Config:
        from_attributes = True

class UserInDB(User): # For internal use, includes hashed_password
    hashed_password: str


# --- Auth Tokens ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel): # Renamed from TokenData for clarity
    sub: Optional[str] = None # 'sub' (subject) is standard claim for user identifier (username as per original TokenData)
    # exp: Optional[int] = None # Expiration is handled by JWT library
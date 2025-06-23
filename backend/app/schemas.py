from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, date

# Constants for field examples
class FieldExamples:
    PROJECT_NAME = "LifeLog Development"
    PROJECT_NAME_UPDATED = "LifeLog Core Development"
    TIMELINE_TITLE = "Working on API design document"
    TIMELINE_SUMMARY = "Detailed planning for v1 endpoints and data models."
    TIMELINE_TITLE_UPDATED = "Refining API design"
    TIMELINE_SUMMARY_UPDATED = "Added error handling and pagination details."
    EVENT_SOURCE = "activitywatch_aw-watcher-window"
    EVENT_ID_1 = "a1b2c3d4-e5f6-7890-1234-567890abcdef"
    EVENT_ID_2 = "b2c3d4e5-f6a7-8901-2345-67890abcdef0"

# --- Base Models & Common ---
class HTTPError(BaseModel):
    detail: Any

class ErrorDetail(BaseModel):
    loc: Optional[List[str]] = None
    msg: str
    type: str

# --- Project ---
class ProjectBase(BaseModel):
    name: str = Field(..., json_schema_extra={'example': FieldExamples.PROJECT_NAME}, min_length=1)

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, json_schema_extra={'example': FieldExamples.PROJECT_NAME_UPDATED}, min_length=1)

class Project(ProjectBase):
    id: UUID

    class Config:
        from_attributes = True

# --- Timeline Entry ---
class TimelineEntryBase(BaseModel):
    start_time: datetime
    end_time: datetime
    title: str = Field(..., json_schema_extra={'example': FieldExamples.TIMELINE_TITLE}, min_length=1)
    summary: Optional[str] = Field(None, json_schema_extra={'example': FieldExamples.TIMELINE_SUMMARY})
    project_id: Optional[UUID] = Field(None)

class TimelineEntryCreate(TimelineEntryBase):
    source_event_ids: Optional[List[UUID]] = Field(
        None, 
        json_schema_extra={'example': [FieldExamples.EVENT_ID_1, FieldExamples.EVENT_ID_2]}
    )

class TimelineEntryUpdate(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    title: Optional[str] = Field(None, json_schema_extra={'example': FieldExamples.TIMELINE_TITLE_UPDATED}, min_length=1)
    summary: Optional[str] = Field(None, json_schema_extra={'example': FieldExamples.TIMELINE_SUMMARY_UPDATED})
    project_id: Optional[UUID] = Field(None)
    source_event_ids: Optional[List[UUID]] = Field(None)

class TimelineEntry(TimelineEntryBase):
    id: UUID
    local_day: date
    project: Optional[Project] = None

    class Config:
        from_attributes = True

# --- Event (Raw Data) ---
class EventBase(BaseModel):
    source: str = Field(..., json_schema_extra={'example': FieldExamples.EVENT_SOURCE})
    event_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    payload: Dict

class Event(EventBase):
    id: UUID
    local_day: date

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
    username: str

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class User(UserBase):
    id: UUID

    class Config:
        from_attributes = True

class UserInDB(User):
    """Internal user model that includes sensitive data."""
    hashed_password: str

# --- Auth Tokens ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    """JWT token payload model."""
    sub: Optional[str] = None
"""
Central data contracts used across the project.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

class TimelineEntry(BaseModel):
    """
    An enriched slice of time in the user's day.
    """
    start: datetime = Field(..., description="UTC start timestamp")
    end:   datetime = Field(..., description="UTC end timestamp")
    activity: str   = Field(..., description="High-level verb phrase, e.g. '3 D modelling'")
    project: Optional[str] = Field(None, description="Name of project/course, if inferrable")
    location: Optional[str] = Field(None, description="User-friendly place name")
    notes: str = Field(..., description="1-2 sentence free-form summary")

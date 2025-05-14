from __future__ import annotations
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

class TimelineEntry(BaseModel):
    """
    A high-level activity entry inferred from raw usage data.
    """
    start: datetime = Field(..., description="UTC start timestamp")
    end:   datetime = Field(..., description="UTC end timestamp")
    activity: str = Field(..., description="Short verb phrase, e.g. '3D modelling'")
    project: Optional[str] = Field(None, description="Optional project/course name")
    location: Optional[str] = Field(None, description="Optional location/place name")
    notes: str = Field(..., description="1–2 sentence summary")

    class Config:
        # Keep epoch millis out of the schema
        json_encoders = {datetime: lambda dt: dt.isoformat() + "Z"}

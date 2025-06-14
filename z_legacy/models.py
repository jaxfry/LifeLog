from __future__ import annotations
from datetime import datetime, timezone  # Added timezone
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
        
        @staticmethod
        def serialize_datetime_as_iso_z(dt: datetime) -> str:
            # Ensure datetime is in UTC
            if dt.tzinfo is None:
                # If datetime is naive, assume it's UTC
                dt_utc = dt.replace(tzinfo=timezone.utc)
            else:
                # If datetime is aware, convert to UTC
                dt_utc = dt.astimezone(timezone.utc)
            
            # Format to ISO 8601 string.
            # dt.isoformat() for a UTC datetime will produce 'YYYY-MM-DDTHH:MM:SS+00:00'
            # or 'YYYY-MM-DDTHH:MM:SS.ffffff+00:00'.
            # Replace '+00:00' with 'Z' for the standard UTC designator.
            return dt_utc.isoformat().replace("+00:00", "Z")

        json_encoders = {
            datetime: serialize_datetime_as_iso_z
        }

# central_server/processing_service/models.py

import logging
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Dict, Any
from datetime import date, datetime, timezone, timedelta

log = logging.getLogger(__name__)

# --- Models for data coming from RabbitMQ after initial deserialization ---
# This is based on central_server/ingestion_service/models.py
class InputLogEvent(BaseModel):
    """Represents a single event as received from the ingestion service."""
    timestamp: datetime # This is likely the start_time for window/web events
    type: str # e.g., "window", "web", "afk"
    data: Dict[str, Any] # Contains app, title, url, duration for AFK, etc.

class InputLogPayload(BaseModel):
    """Represents the entire payload received from RabbitMQ."""
    events: list[InputLogEvent]
    source_id: str

class ProcessingRequestPayload(BaseModel):
    """
    Payload for triggering an on-demand batch processing job for a specific day.
    """
    target_date: date


# --- Models for internal processing ---
class ProcessingEventData(BaseModel):
    """
    Represents a structured event ready for aggregation and LLM processing.
    This is transformed from InputLogEvent.
    """
    event_id: Optional[str] = None # Optional: if we want to trace back to an original ID
    start_time: datetime
    end_time: datetime # May need to be calculated for some event types
    duration_s: float # Calculated from start_time and end_time
    app: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    event_type: str # Original event type, e.g. "window", "web", "afk"

    @field_validator('start_time', 'end_time', mode='before')
    @classmethod
    def ensure_utc(cls, v):
        if isinstance(v, str):
            dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
            return dt.astimezone(timezone.utc)
        if isinstance(v, datetime):
            return v.astimezone(timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)
        raise ValueError("Invalid datetime format")

    @model_validator(mode='after')
    def calculate_duration_if_needed(self):
        if self.start_time and self.end_time:
            if self.start_time > self.end_time:
                log.warning(f"ProcessingEventData: start_time {self.start_time} is after end_time {self.end_time}. Swapping.")
                self.start_time, self.end_time = self.end_time, self.start_time
            
            self.duration_s = (self.end_time - self.start_time).total_seconds()
            
            if self.duration_s < 0: # Should not happen after swap
                log.error(f"Negative duration calculated for event: {self.model_dump_json()}")
                self.duration_s = 0
        return self


class TimelineEntry(BaseModel):
    """Pydantic model for timeline entries returned by LLM."""
    start: datetime = Field(description="Start time UTC ISO format.")
    end: datetime = Field(description="End time UTC ISO format.")
    activity: str = Field(description="Short descriptive activity phrase.")
    project: Optional[str] = Field(default=None, description="Project/course name.")
    notes: Optional[str] = Field(default=None, description="1-2 sentence summary.")

    @field_validator('start', 'end', mode='before')
    @classmethod
    def parse_datetime_utc(cls, v):
        if isinstance(v, str):
            dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
            return dt.astimezone(timezone.utc)
        if isinstance(v, datetime):
            return v.astimezone(timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)
        raise ValueError("Invalid datetime format")

    @model_validator(mode='after')
    def check_start_before_end(self):
        if self.start and self.end:
            if self.start > self.end:
                log.warning(f"TimelineEntry: Start time {self.start} is after end time {self.end}. Swapping them.")
                self.start, self.end = self.end, self.start
            if self.start == self.end: # Ensure end is at least 1s after start
                log.warning(f"TimelineEntry: Start time {self.start} is equal to end time {self.end}. Adjusting end time by 1 sec.")
                self.end = self.start + timedelta(seconds=1)
        return self

if __name__ == "__main__":
    # Example Usage
    logging.basicConfig(level=logging.DEBUG)

    # Example InputLogEvent (simulating what comes from RabbitMQ)
    raw_event_data = {
        "timestamp": "2023-10-26T10:00:00Z",
        "type": "window",
        "data": {
            "app": "VS Code",
            "title": "editing models.py",
            "duration": 60.0 # Assuming ingestion service might provide duration for some events
        }
    }
    input_event = InputLogEvent(**raw_event_data)
    log.info(f"Parsed InputLogEvent: {input_event.model_dump_json(indent=2)}")

    # Transforming InputLogEvent to ProcessingEventData
    # This logic will typically be in the worker
    start_dt = input_event.timestamp
    # If duration is in data, use it, otherwise assume some default or handle event type
    duration_val = input_event.data.get("duration")
    if duration_val is not None:
        end_dt = start_dt + timedelta(seconds=duration_val)
        proc_event = ProcessingEventData(
            start_time=start_dt,
            end_time=end_dt,
            duration_s=duration_val,
            app=input_event.data.get("app"),
            title=input_event.data.get("title"),
            url=input_event.data.get("url"),
            event_type=input_event.type
        )
        log.info(f"ProcessingEventData: {proc_event.model_dump_json(indent=2)}")
    else:
        log.warning("No duration found in event data; cannot create ProcessingEventData.")

    # Example LLM output (simulate TimelineEntry creation)
    llm_output_example = {
        "start": "2023-10-26T10:00:00Z",
        "end": "2023-10-26T10:30:00Z",
        "activity": "Debugging payment API bug",
        "project": "LifeLog",
        "notes": "Worked on payment API integration."
    }
    # Convert string datetimes to datetime objects for TimelineEntry
    timeline_entry = TimelineEntry(
        start=datetime.fromisoformat(llm_output_example["start"].replace('Z', '+00:00')),
        end=datetime.fromisoformat(llm_output_example["end"].replace('Z', '+00:00')),
        activity=llm_output_example["activity"],
        project=llm_output_example["project"],
        notes=llm_output_example["notes"]
    )
    log.info(f"TimelineEntry: {timeline_entry.model_dump_json(indent=2)}")

    # Example with invalid times (should trigger swap)
    invalid_llm_output = {
        "start": "2023-10-26T10:30:00Z",
        "end": "2023-10-26T10:00:00Z",
        "activity": "Debugging payment API bug",
        "project": "LifeLog",
        "notes": "Worked on payment API integration."
    }
    invalid_entry = TimelineEntry(
        start=datetime.fromisoformat(invalid_llm_output["start"].replace('Z', '+00:00')),
        end=datetime.fromisoformat(invalid_llm_output["end"].replace('Z', '+00:00')),
        activity=invalid_llm_output["activity"],
        project=invalid_llm_output["project"],
        notes=invalid_llm_output["notes"]
    )
    log.info(f"TimelineEntry (invalid): {invalid_entry.model_dump_json(indent=2)}")
from pydantic import BaseModel
from typing import List, Dict, Any
import datetime

class LogEvent(BaseModel):
    timestamp: datetime.datetime
    type: str
    data: Dict[str, Any]

class LogPayload(BaseModel):
    events: List[LogEvent]
    source_id: str # To identify the daemon instance sending the data
    sent_at_timestamp_utc: datetime.datetime
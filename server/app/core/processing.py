from sqlalchemy.ext.asyncio import AsyncSession
from app.models.data import RawLog, Event
from app.loader.runner import run_normalization
from uuid import UUID
from typing import List
from datetime import datetime, timezone
from app.core.utils.time import get_logical_date
from app.core.logger import get_logger

logger = get_logger(__name__)

async def process_log(session: AsyncSession, log_id: UUID) -> List[Event]:
    """
    Loads a RawLog, runs the extension processor, and saves Events.
    """
    log = await session.get(RawLog, log_id)
    if not log:
        logger.error(f"Log {log_id} not found")
        return []
    
    logger.info(f"Processing log {log_id} with extension {log.extension_id}")
    events_data = run_normalization(log.extension_id, log.payload)
    
    # Determine timezone from client_timezone
    timezone_str = log.client_timezone if log.client_timezone else "UTC"
    iana_timezone = log.iana_timezone if log.iana_timezone else "UTC"

    created_events = []
    for event_data in events_data:
        # Determine logical date from the event's actual start_time_utc or timestamp
        # Fall back to log timestamp or 'now' if missing
        start_time_iso = event_data.get("data", {}).get("timestamp") or event_data.get("data", {}).get("start_time")
        
        event_dt = log.received_at.replace(tzinfo=timezone.utc)
        if start_time_iso:
            try:
                # Assuming AW outputs UTC isoformat
                parsed_dt = datetime.fromisoformat(start_time_iso.replace('Z', '+00:00'))
                event_dt = parsed_dt.astimezone(timezone.utc)
            except ValueError:
                pass
                
        event_logical_date = get_logical_date(event_dt, iana_timezone)

        event = Event(
            source_log_id=log.id,
            type=event_data.get("type", "unknown"),
            data=event_data.get("data", {}),
            timezone=timezone_str,
            iana_timezone=iana_timezone,
            logical_date=event_logical_date,
            processing_version=1 
        )
        session.add(event)
        created_events.append(event)
    
    await session.commit()
    logger.info(f"Created {len(created_events)} events")
    return created_events

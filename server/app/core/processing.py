from sqlalchemy.ext.asyncio import AsyncSession
from app.models.data import RawLog, Event
from app.loader.runner import run_normalization
from uuid import UUID
from typing import List

async def process_log(session: AsyncSession, log_id: UUID) -> List[Event]:
    """
    Loads a RawLog, runs the extension processor, and saves Events.
    """
    log = await session.get(RawLog, log_id)
    if not log:
        print(f"Log {log_id} not found")
        return []
    
    print(f"Processing log {log_id} with extension {log.extension_id}")
    events_data = run_normalization(log.extension_id, log.payload)
    
    # Determine timezone from client_timezone
    timezone_str = log.client_timezone if log.client_timezone else "UTC"

    created_events = []
    for event_data in events_data:
        event = Event(
            source_log_id=log.id,
            type=event_data.get("type", "unknown"),
            data=event_data.get("data", {}),
            timezone=timezone_str,
            processing_version=1 
        )
        session.add(event)
        created_events.append(event)
    
    await session.commit()
    print(f"Created {len(created_events)} events")
    return created_events

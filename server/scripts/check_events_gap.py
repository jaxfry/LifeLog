
import asyncio
import os
import sys
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_
from datetime import datetime

# Add server directory to path so imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.dirname(current_dir)
sys.path.append(server_dir)

from app.core.db import engine
from app.models.data import Event

async def main():
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # Check for events where the payload timestamp falls in the gap
        # Since created_at is unreliable (set to ingestion time), we must scan events.
        # To avoid scanning ALL events, we can filter by created_at >= today (since we know they were ingested today)
        
        ingest_start = datetime(2025, 12, 2, 0, 0)
        stmt = select(Event).where(Event.created_at >= ingest_start)
        
        result = await session.execute(stmt)
        events = result.scalars().all()
        
        gap_start = datetime(2025, 11, 30, 0, 30).timestamp()
        gap_end = datetime(2025, 12, 1, 9, 30).timestamp()
        
        found_events = []
        
        for event in events:
            ts_str = event.data.get("timestamp") or event.data.get("start_time")
            if ts_str:
                try:
                    dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    ts = dt.timestamp()
                    if gap_start <= ts <= gap_end:
                        found_events.append(event)
                except ValueError:
                    pass
        
        print(f"Found {len(found_events)} events with timestamps in the gap period ({gap_start} to {gap_end}):")
        if found_events:
            print(f"First event: {found_events[0].data.get('timestamp') or found_events[0].data.get('start_time')} - {found_events[0].type}")
            print(f"Last event: {found_events[-1].data.get('timestamp') or found_events[-1].data.get('start_time')} - {found_events[-1].type}")
            
            # Check if they are assigned to a session
            assigned_count = sum(1 for e in found_events if e.session_id)
            print(f"Assigned to session: {assigned_count} / {len(found_events)}")
            
            if assigned_count > 0:
                # Print unique session IDs
                session_ids = set(e.session_id for e in found_events if e.session_id)
                print(f"Session IDs: {session_ids}")

if __name__ == "__main__":
    asyncio.run(main())

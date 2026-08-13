import asyncio
import json
import os
from datetime import UTC

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from app.models.ingest import Event
from app.models.processing import Session

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://lifelog:lifelogpassword@db:5432/lifelog_db")

async def get_chunk():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Find a session with a decent number of events to represent a "chunk"
        stmt = select(Session).where(Session.status == "completed").order_by(Session.start_time.desc()).limit(10)
        result = await session.execute(stmt)
        sessions = result.scalars().all()

        target_session = None
        target_events = []
        for s in sessions:
            # Get event count
            event_stmt = select(Event).where(Event.session_id == s.id)
            event_result = await session.execute(event_stmt)
            events = event_result.scalars().all()

            if len(events) > 5:  # Arbitrary filter to find a "meaty" session
                target_session = s
                target_events = events
                break

        if not target_session:
            print("No suitable session found.")
            return

        print(f"Found Session ID: {target_session.id}")
        print(f"Time Range: {target_session.start_time} - {target_session.end_time}")
        print(f"Event Count: {len(target_events)}")
        print("-" * 40)

        events_data = []
        for event in target_events:
            utc_dt = event.start_time.replace(tzinfo=UTC)
            local_time_iso = utc_dt.isoformat()

            evt_dict = {
                "time": local_time_iso,
                "type": event.event_type,
                "data": event.data
            }
            events_data.append(evt_dict)

        print(json.dumps(events_data, indent=2))


if __name__ == "__main__":
    asyncio.run(get_chunk())

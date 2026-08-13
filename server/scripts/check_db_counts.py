import asyncio

from sqlalchemy import func
from sqlmodel import select

from app.core.database import get_session
from app.models.ingest import Event, RawLog
from app.models.processing import Session, TimelineEntry


async def check_counts():
    async for session in get_session():
        # Count RawLogs
        res = await session.execute(select(func.count()).select_from(RawLog))
        raw_logs_count = res.scalar_one()

        # Count Events
        res = await session.execute(select(func.count()).select_from(Event))
        events_count = res.scalar_one()

        # Count Sessions
        res = await session.execute(select(func.count()).select_from(Session))
        sessions_count = res.scalar_one()

        # Count Timeline entries
        res = await session.execute(select(func.count()).select_from(TimelineEntry))
        timeline_count = res.scalar_one()

        print(f"RawLogs: {raw_logs_count}")
        print(f"Events: {events_count}")
        print(f"Sessions: {sessions_count}")
        print(f"Timeline Entries: {timeline_count}")

        # If timeline entries exist, print the last few to see what they are
        if timeline_count > 0:
            res = await session.execute(select(TimelineEntry).order_by(TimelineEntry.start_time.desc()).limit(5))
            entries = res.scalars().all()
            print("\nRecent Timeline Entries:")
            for entry in entries:
                print(f"- {entry.start_time} -> {entry.end_time}: {entry.activity} ({entry.notes})")

if __name__ == "__main__":
    asyncio.run(check_counts())

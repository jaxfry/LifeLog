
import asyncio
import os
import sys

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

# Add server directory to path so imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.dirname(current_dir)
sys.path.append(server_dir)

from app.core.database import engine
from app.models.processing import TimelineEntry


async def main():
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        stmt = select(TimelineEntry).order_by(desc(TimelineEntry.start_time)).limit(5)
        result = await session.execute(stmt)
        entries = result.scalars().all()

        print(f"Found {len(entries)} timeline entries:")
        for entry in entries:
            print(f"--- Entry {entry.id} ---")
            print(f"Start: {entry.start_time}")
            print(f"End: {entry.end_time}")
            print(f"Activity: {entry.activity}")
            print(f"Notes: {entry.notes}")
            print(f"Timezone: {entry.logical_date}")
            print(f"Tags: {entry.tags}")
            print(f"Category: {entry.category}")
            print(f"Entities: {entry.tags}")

if __name__ == "__main__":
    asyncio.run(main())

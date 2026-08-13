
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
        stmt = select(TimelineEntry).order_by(desc(TimelineEntry.start_time)).limit(20)
        result = await session.execute(stmt)
        entries = result.scalars().all()

        print(f"Found {len(entries)} timeline entries:")
        for entry in entries:
            print(f"- {entry.start_time} (UTC): {entry.activity} [{entry.id}]")

if __name__ == "__main__":
    asyncio.run(main())

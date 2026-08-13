
import asyncio
import os
import sys
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

# Add server directory to path so imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.dirname(current_dir)
sys.path.append(server_dir)

from app.core.database import engine
from app.models.processing import Session


async def main():
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        # Check for sessions starting between Nov 29 and Dec 2
        start = datetime(2025, 11, 29, 0, 0)
        end = datetime(2025, 12, 2, 23, 59)

        stmt = select(Session).where(
            and_(Session.start_time >= start, Session.start_time <= end)
        ).order_by(Session.start_time)

        result = await session.execute(stmt)
        sessions = result.scalars().all()

        print(f"Found {len(sessions)} sessions between {start} and {end}:")
        for s in sessions:
            print(f"- {s.start_time} to {s.end_time} | Status: {s.status} | ID: {s.id}")

if __name__ == "__main__":
    asyncio.run(main())

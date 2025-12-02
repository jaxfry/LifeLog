
import asyncio
import os
import sys
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, timedelta

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
        # Check for events in the last 10 minutes
        start = datetime.utcnow() - timedelta(minutes=10)
        
        stmt = select(Event).where(Event.created_at >= start).order_by(desc(Event.created_at))
        
        result = await session.execute(stmt)
        events = result.scalars().all()
        
        print(f"Found {len(events)} events in the last 10 minutes:")
        for event in events:
            print(f"- {event.created_at} (UTC): {event.type} [{event.id}]")

if __name__ == "__main__":
    asyncio.run(main())

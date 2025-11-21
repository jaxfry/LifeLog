import asyncio
import os
import sys
from datetime import date, datetime

# Add server directory to path so imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.dirname(current_dir)
sys.path.append(server_dir)

from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import engine
from app.core.sessionizer import run_sessionizer
from app.core.timeline_processor import process_pending_sessions

async def main():
    print("Running processing pipeline...")
    
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        print("Running sessionizer...")
        await run_sessionizer(session)
        print("Processing pending sessions...")
        await process_pending_sessions(session)

if __name__ == "__main__":
    asyncio.run(main())

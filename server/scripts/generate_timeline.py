import asyncio
import os
import sys

# Add server directory to path so imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.dirname(current_dir)
sys.path.append(server_dir)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import engine
from app.services.sessionizer import run_sessionizer
from app.services.timeline import process_pending_sessions


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

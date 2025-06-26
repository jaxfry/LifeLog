import asyncio
from backend.app.core.settings import Settings
from backend.app.processing.timeline import process_pending_events_sync
from backend.app.core.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

async def main():
    settings = Settings()
    async for session in get_db():
        print("Clearing event_state table...")
        await session.execute(text("DELETE FROM event_state"))
        print("Reprocessing timeline...")
        await process_pending_events_sync(session, settings)
        print("Done.")
        await session.commit()

if __name__ == "__main__":
    asyncio.run(main())
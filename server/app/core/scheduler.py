from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.db import engine
from app.core.sessionizer import run_sessionizer
from app.core.timeline_processor import process_pending_sessions
from app.core.logger import get_logger

scheduler = AsyncIOScheduler()

logger = get_logger(__name__)

async def run_processing_job():
    logger.info("Running processing job...")
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # 1. Sessionize new events
        await run_sessionizer(session)
        # 2. Process pending sessions
        await process_pending_sessions(session)

def start_scheduler():
    # Run processing job every 15 minutes
    scheduler.add_job(run_processing_job, 'interval', minutes=15)
    
    scheduler.start()

def stop_scheduler():
    scheduler.shutdown()

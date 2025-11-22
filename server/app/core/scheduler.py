from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.db import engine
from app.core.sessionizer import run_sessionizer
from app.core.timeline_processor import process_pending_sessions
from app.core.rebuilder import process_dirty_sessions
from app.core.daily_summary import generate_daily_summary
from app.core.logger import get_logger
from datetime import datetime, timedelta

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
        # 3. Process dirty sessions
        await process_dirty_sessions(session)

async def run_daily_summary_job():
    """
    Generates the daily summary for the previous day.
    """
    logger.info("Running daily summary job...")
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Target yesterday
        yesterday = datetime.now() - timedelta(days=1)
        await generate_daily_summary(session, yesterday)

def start_scheduler():
    # Run processing job every 15 minutes
    scheduler.add_job(run_processing_job, 'interval', minutes=15)
    
    # Run daily summary at 01:00 AM every day
    scheduler.add_job(run_daily_summary_job, 'cron', hour=1, minute=0)
    
    scheduler.start()

def stop_scheduler():
    scheduler.shutdown()

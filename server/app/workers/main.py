import os
import traceback
from arq import create_pool
from arq.connections import RedisSettings
from app.core.db import engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.processing import process_log
from app.models.audit import Failure
from uuid import UUID

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

async def startup(ctx):
    print("Worker starting...")
    # Initialize DB engine if needed, though it's global in db.py
    pass

async def shutdown(ctx):
    print("Worker shutting down...")
    pass

async def task_normalize_log(ctx, log_id_str: str):
    """
    Task to normalize a log entry.
    """
    log_id = UUID(log_id_str)
    print(f"Worker: Processing log {log_id}")
    
    # Create a new session for this task
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        try:
            events = await process_log(session, log_id)
            print(f"Worker: Created {len(events)} events for log {log_id}")
        except Exception as e:
            print(f"Worker: Error processing log {log_id}: {e}")
            # Log to failures table
            failure = Failure(
                traceback=traceback.format_exc(),
                context={"log_id": str(log_id), "error": str(e)}
            )
            session.add(failure)
            await session.commit()
            # Do not re-raise, so the worker keeps running and considers this "handled"

class WorkerSettings:
    functions = [task_normalize_log]
    redis_settings = RedisSettings.from_dsn(REDIS_URL)
    on_startup = startup
    on_shutdown = shutdown

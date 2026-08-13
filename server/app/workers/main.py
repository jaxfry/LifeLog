import os
import traceback
from uuid import UUID

from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import engine
from app.core.logger import get_logger
from app.workers.files import task_process_file, task_process_file_batch
from app.workers.process import process_log

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

logger = get_logger(__name__)


async def startup(ctx):
    logger.info("Worker starting...")


async def shutdown(ctx):
    logger.info("Worker shutting down...")


async def task_normalize_log(ctx, log_id_str: str):
    log_id = UUID(log_id_str)
    logger.info("Worker: Processing log %s", log_id)

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        try:
            events = await process_log(session, log_id)
            logger.info("Worker: Created %d events for log %s", len(events), log_id)
        except Exception as e:
            logger.error("Worker: Error processing log %s: %s", log_id, e)
            logger.error(traceback.format_exc())


class WorkerSettings:
    functions = [task_normalize_log, task_process_file, task_process_file_batch]
    redis_settings = RedisSettings.from_dsn(REDIS_URL)

import logging
import sys
import os
from datetime import date, timedelta, datetime, timezone

# Add project root to sys.path to allow for sibling imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import asyncio
from sqlalchemy import select
# Imports from the new processing service structure
from central_server.processing_service.batch_processor import run_batch_processing
from central_server.processing_service.db_session import get_db_session_async, check_db_connection_async
from central_server.processing_service.db_models import Event as EventOrm

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


async def get_date_range(session):
    """
    Determines the range of dates that have events in the database.
    """
    min_date_result = await session.execute(
        select(EventOrm.local_day).order_by(EventOrm.local_day.asc()).limit(1)
    )
    max_date_result = await session.execute(
        select(EventOrm.local_day).order_by(EventOrm.local_day.desc()).limit(1)
    )
    min_date = min_date_result.scalar_one_or_none()
    max_date = max_date_result.scalar_one_or_none()

    return min_date, max_date


async def main():
    """
    Iterates through all days with available event data and runs batch processing for each.
    """
    log.info("--- Starting full timeline reprocessing ---")

    if not await check_db_connection_async():
        log.error("Database connection failed. Aborting reprocessing.")
        return

    async with get_db_session_async() as db_session:
        start_date, end_date = await get_date_range(db_session)

        if not start_date or not end_date:
            log.info("No events found in the database. Nothing to reprocess.")
            return

        log.info(f"Found data spanning from {start_date.isoformat()} to {end_date.isoformat()}.")
        
        current_date = start_date
        while current_date <= end_date:
            log.info(f"--- Queueing reprocessing for: {current_date.isoformat()} ---")
            try:
                # Use on-demand trigger time for precise reprocessing
                await run_batch_processing(current_date, process_at_utc=datetime.now(timezone.utc))
            except Exception as e:
                log.error(f"An error occurred while processing {current_date.isoformat()}: {e}", exc_info=True)
            
            current_date += timedelta(days=1)

    log.info("--- Full timeline reprocessing FINISHED ---")


if __name__ == "__main__":
    asyncio.run(main())
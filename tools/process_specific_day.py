import logging
import sys
import os
import asyncio
from datetime import datetime, date, time, timezone as pytimezone, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, delete

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app.core.db import SessionLocal
from backend.app.core.settings import settings
from backend.app.ingestion.activitywatch import ingest_activitywatch_data
from backend.app.processing.timeline import process_pending_events_sync
from backend.app.models import Event, TimelineEntry, event_state

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

async def process_day(target_date_str: str):
    log.info(f"--- Starting processing for specific day: {target_date_str} ---")
    try:
        target_day = date.fromisoformat(target_date_str)
    except ValueError:
        log.error(f"Invalid date format: {target_date_str}. Please use YYYY-MM-DD.")
        return
    try:
        local_tz = ZoneInfo(settings.LOCAL_TZ)
    except Exception as e:
        log.warning(f"Failed to load local timezone '{settings.LOCAL_TZ}': {e}. Using UTC.")
        local_tz = pytimezone.utc
    start_local = datetime.combine(target_day, time.min, tzinfo=local_tz)
    end_local = datetime.combine(target_day, time.max, tzinfo=local_tz)
    start_utc = start_local.astimezone(pytimezone.utc)
    end_utc = end_local.astimezone(pytimezone.utc)
    log.info(f"Target local day: {target_day.isoformat()} ({settings.LOCAL_TZ})")
    log.info(f"Calculated UTC window for ingestion: {start_utc} -> {end_utc}")
    async with SessionLocal() as session:
        try:
            # 1. Clear event_state for the target day to ensure reprocessing if needed
            log.info(f"Clearing event_state for events on local_day = {target_day.isoformat()}")
            event_ids_stmt = select(Event.id).where(Event.local_day == target_day)
            result = await session.execute(event_ids_stmt)
            event_ids = [row for row in result.scalars().all()]
            if event_ids:
                del_stmt = delete(event_state).where(event_state.c.event_id.in_(event_ids))
                await session.execute(del_stmt)
                await session.commit()
                log.info(f"Cleared event_state for {len(event_ids)} events on {target_day.isoformat()}")
            else:
                log.info(f"No events found for {target_day.isoformat()}, skipping event_state clear.")
            # 2. Ingest ActivityWatch data for the specific day (now async/Postgres)
            log.info(f"Ingesting ActivityWatch data for {start_utc} -> {end_utc}")
            await ingest_activitywatch_data(session, settings, start_utc, end_utc)
            log.info("ActivityWatch data ingestion complete.")
            # 3. Process pending events (now async/Postgres)
            log.info("Processing timeline for pending events...")
            await process_pending_events_sync(session, settings)
            log.info("Timeline processing complete.")
            # Final stats
            event_count_stmt = select(Event).where(Event.local_day == target_day)
            timeline_count_stmt = select(TimelineEntry).where(TimelineEntry.local_day == target_day)
            event_count = len((await session.execute(event_count_stmt)).scalars().all())
            timeline_entry_count = len((await session.execute(timeline_count_stmt)).scalars().all())
            log.info(f"Events in DB for {target_day.isoformat()}: {event_count}")
            log.info(f"Timeline entries in DB for {target_day.isoformat()}: {timeline_entry_count}")
            log.info(f"\n--- Processing for {target_date_str} FINISHED ---")
        except Exception as e:
            log.error(f"An error occurred during processing for {target_date_str}: {e}", exc_info=True)
            await session.rollback()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        date_to_process = sys.argv[1]
    else:
        yesterday = (datetime.now(pytimezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        date_to_process = input(f"Enter date to process (YYYY-MM-DD) [default: {yesterday}]: ") or yesterday
        log.warning(f"No date provided as command line argument. Using: {date_to_process}")
    asyncio.run(process_day(date_to_process))
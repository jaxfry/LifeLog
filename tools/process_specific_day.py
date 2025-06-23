import logging
import sys
import os # Add os import
from datetime import datetime, date, time, timezone as pytimezone, timedelta
from zoneinfo import ZoneInfo

# Add project root to sys.path to allow for absolute imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from backend.app.core.db import get_db_connection
from backend.app.core.settings import settings
from backend.app.ingestion.activitywatch import ingest_activitywatch_data
from backend.app.processing.timeline import process_pending_events_sync

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def process_day(target_date_str: str):
    """
    Ingests and processes timeline data for a specific local day.

    Args:
        target_date_str: The target day in "YYYY-MM-DD" format.
    """
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

    # Determine start and end of the target day in local time
    start_local = datetime.combine(target_day, time.min, tzinfo=local_tz)
    end_local = datetime.combine(target_day, time.max, tzinfo=local_tz)

    # Convert to UTC for ActivityWatch ingestion
    start_utc = start_local.astimezone(pytimezone.utc)
    end_utc = end_local.astimezone(pytimezone.utc)

    log.info(f"Target local day: {target_day.isoformat()} ({settings.LOCAL_TZ})")
    log.info(f"Calculated UTC window for ingestion: {start_utc} -> {end_utc}")

    con = get_db_connection()
    try:
        # 1. Clear event_state for the target day to ensure reprocessing if needed
        log.info(f"Clearing event_state for events on local_day = {target_day.isoformat()}")
        # The events table stores local_day directly, so we use that.
        delete_query = """
        DELETE FROM event_state
        WHERE event_id IN (SELECT id FROM events WHERE local_day = ?);
        """
        result = con.execute(delete_query, [target_day])
        log.info(f"Cleared {result.rowcount if result.rowcount is not None else 'unknown'} entries from event_state for {target_day.isoformat()}")
        con.commit() # Commit this change before proceeding

        # 2. Ingest ActivityWatch data for the specific day
        log.info(f"Ingesting ActivityWatch data for {start_utc} -> {end_utc}")
        ingest_activitywatch_data(con, settings, start_utc, end_utc)
        log.info("ActivityWatch data ingestion complete.")

        # 3. Process pending events (which should now include the target day)
        log.info("Processing timeline for pending events...")
        process_pending_events_sync(con, settings)
        log.info("Timeline processing complete.")

        log.info(f"\n--- Processing for {target_date_str} FINISHED ---")

        # Optional: Basic checks
        event_result = con.execute("SELECT count(*) FROM events WHERE local_day = ?", [target_day]).fetchone()
        event_count = event_result[0] if event_result else 0
        
        timeline_result = con.execute("SELECT count(*) FROM timeline_entries WHERE local_day = ?", [target_day]).fetchone()
        timeline_entry_count = timeline_result[0] if timeline_result else 0

        log.info(f"Events in DB for {target_day.isoformat()}: {event_count}")
        log.info(f"Timeline entries in DB for {target_day.isoformat()}: {timeline_entry_count}")

    except Exception as e:
        log.error(f"An error occurred during processing for {target_date_str}: {e}", exc_info=True)
        if con: # Check if con was successfully initialized
            con.rollback()
    finally:
        if con: # Check if con was successfully initialized
            con.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        date_to_process = sys.argv[1]
    else:
        # Fallback to a default or prompt if you prefer
        # For this example, let's use yesterday as a default if no arg is given
        yesterday = (datetime.now(pytimezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        date_to_process = input(f"Enter date to process (YYYY-MM-DD) [default: {yesterday}]: ") or yesterday
        # date_to_process = "2023-10-26" # Or hardcode for testing
        log.warning(f"No date provided as command line argument. Using: {date_to_process}")
    
    process_day(date_to_process)
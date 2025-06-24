# backend/app/daemon/realtime_watcher.py
import logging
import time
import queue
import threading # Added for typing
from datetime import datetime, timezone, timedelta

from aw_client import ActivityWatchClient
from duckdb import DuckDBPyConnection
import polars as pl

from backend.app.core.db import get_db_connection, close_db_connection
from backend.app.core.settings import settings
from backend.app.core.utils import with_db_write_retry
from backend.app.ingestion.activitywatch import (
    HashGenerator,
    DIGITAL_ACTIVITY_EVENT_TYPE,
    ACTIVITYWATCH_SOURCE,
)

log = logging.getLogger(__name__)

# This queue is for AURA to consume immediately.
aura_event_queue = queue.Queue()

# --- Constants for the Polling Strategy ---
POLLING_INTERVAL_SECONDS = 10  # How often to check for new events. 5-15s is a good range.
QUERY_OVERLAP_SECONDS = 5    # Increased overlap slightly for more robustness


@with_db_write_retry()
def write_events_to_db(events_df: pl.DataFrame):
    """
    Writes a DataFrame of new events to the database in a single transaction.
    This is much more efficient than writing event by event.
    """
    if events_df.is_empty():
        return

    con: DuckDBPyConnection | None = None
    try:
        con = get_db_connection()
        con.register('df_to_insert', events_df)
        # Use a single transaction for the whole batch
        con.begin()
        
        # Insert base events
        con.execute("""
            INSERT INTO events (id, source, event_type, start_time, end_time, payload_hash)
            SELECT gen_random_uuid(), source, event_type::event_kind, start_time, end_time, payload_hash
            FROM df_to_insert
            ON CONFLICT (payload_hash) DO NOTHING;
        """)
        
        # Get the IDs of the events we just inserted (or that already existed)
        # and then insert the detailed data.
        con.execute("""
            CREATE OR REPLACE TEMP TABLE new_events_to_process AS
            SELECT e.id, i.hostname, i.app, i.title, i.url
            FROM df_to_insert AS i
            JOIN events AS e ON i.payload_hash = e.payload_hash;
        """)

        con.execute("""
            INSERT INTO digital_activity_data (event_id, hostname, app, title, url)
            SELECT id, hostname, app, title, url
            FROM new_events_to_process
            ON CONFLICT (event_id) DO NOTHING;
        """)
        
        con.commit()
        log.debug(f"COLD_PATH: Wrote {events_df.height} new events to DB for later processing.")
    except Exception as e:
        log.error(f"Failed to write batch of real-time events to DB: {e}")
        if con:
            con.rollback()
    finally:
        if con:
            con.unregister('df_to_insert')
            close_db_connection(con) # Ensures thread-local is cleared


def main(watcher_status: dict | None = None): # Accept shared status object
    log.info("--- Starting LifeLog Real-Time Watcher (Polling Mode) ---")
    if watcher_status:
        log.info("Watcher status object is enabled for heartbeat and timestamp.")
    aw_client = ActivityWatchClient("lifelog-realtime-watcher")
    # db_con = get_db_connection() # This connection was not used directly in the loop

    # The buckets we want to watch for real-time events
    bucket_ids = [
        settings.AW_WINDOW_BUCKET,
        settings.AW_WEB_BUCKET 
    ]
    log.info(f"Watching buckets: {bucket_ids}")

    # --- STATE VARIABLES ---
    last_event_timestamp = datetime.now(timezone.utc)
    # NEW: A globally persistent set to track all hashes processed in this session.
    # This prevents re-processing events from the query overlap.
    globally_processed_hashes = set()

    try:
        while True:
            try:
                # Define the time window for the new query
                query_start_time = last_event_timestamp - timedelta(seconds=QUERY_OVERLAP_SECONDS)
                query_end_time = datetime.now(timezone.utc)

                all_new_events = []
                for bucket_id in bucket_ids:
                    # Fetch events from the AW server
                    events = aw_client.get_events(
                        bucket_id=bucket_id,
                        start=query_start_time,
                        end=query_end_time,
                        limit=-1
                    )
                    if events:
                        all_new_events.extend(events)

                if not all_new_events:
                    # No new events, but still signal alive and update timestamp
                    if watcher_status:
                        with watcher_status['lock']:
                            # last_event_timestamp here is the timestamp of the last *actual* event seen,
                            # or the initialization time if no events ever seen.
                            watcher_status['last_event_ts'] = last_event_timestamp
                        watcher_status['alive_event'].set()
                        log.debug(f"Signalled alive (no new events). Last actual event ts: {last_event_timestamp.isoformat() if last_event_timestamp else 'N/A'}")
                    time.sleep(POLLING_INTERVAL_SECONDS)
                    continue

                # --- Process the batch of new events ---
                
                # Sort events chronologically to process them in order
                all_new_events.sort(key=lambda e: e.timestamp)
                
                records_for_db = []
                hash_generator = HashGenerator()

                for event in all_new_events:
                    # Update high-water mark regardless of whether we process it
                    last_event_timestamp = max(last_event_timestamp, event.timestamp)
                    
                    event_data = {
                        "app": event.data.get("app"),
                        "title": event.data.get("title"),
                        "url": event.data.get("url"),
                        "start_time": event.timestamp,
                        "end_time": event.timestamp + event.duration,
                    }
                    payload_hash = hash_generator.generate_payload_hash(event_data)
                    
                    # CHANGED: Check against the global set, not a temporary one.
                    if payload_hash in globally_processed_hashes:
                        continue  # Skip this event entirely, we've seen it before.

                    # This is a genuinely new event. Process it.
                    globally_processed_hashes.add(payload_hash)

                    # 1. Feed the Hot Path (for AURA)
                    aura_event_queue.put(event_data)
                    
                    # IMPROVED LOGGING: Provide more context.
                    app_name = event_data['app'] or 'Web'
                    title = event_data['title'] or 'No Title'
                    log_summary = f"{app_name} - {title}"
                    log.info(f"HOT_PATH: Queued new event for AURA: {log_summary[:120]}")

                    # 2. Prepare event for Cold Path DB write
                    db_record = event_data.copy()
                    db_record.update({
                        "payload_hash": payload_hash,
                        "source": ACTIVITYWATCH_SOURCE,
                        "event_type": DIGITAL_ACTIVITY_EVENT_TYPE,
                        "hostname": settings.AW_HOSTNAME,
                    })
                    records_for_db.append(db_record)
                
                if records_for_db:
                    events_df = pl.from_dicts(records_for_db)
                    write_events_to_db(events_df)

                # Signal that the main loop iteration is complete, watcher is alive, and update timestamp
                if watcher_status:
                    with watcher_status['lock']:
                        # last_event_timestamp has been updated with max(event.timestamp) in the loop
                        watcher_status['last_event_ts'] = last_event_timestamp
                    watcher_status['alive_event'].set()
                    log.debug(f"Signalled alive (events processed). Last actual event ts: {last_event_timestamp.isoformat() if last_event_timestamp else 'N/A'}")

            except Exception as e:
                # Catch potential connection errors to aw-server, etc.
                log.error(f"Error in polling loop: {e}", exc_info=True)
                # Wait longer before retrying to avoid spamming a dead server
                time.sleep(POLLING_INTERVAL_SECONDS * 3)
            
            # Wait for the next polling interval
            time.sleep(POLLING_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        log.info("Real-time watcher stopped by user.")
    finally:
        # The db_con initialized at the start of main was removed, so no close needed here.
        # Connections for write_events_to_db are handled within that function.
        log.info("--- LifeLog Real-Time Watcher Shutdown ---")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
    )
    main()
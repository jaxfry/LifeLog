"""
Local Caching for the Daemon.
Uses SQLite to store events before they are sent to the central server.
"""
import sqlite3
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from . import config

log = logging.getLogger(__name__)

DB_PATH = config.LOCAL_CACHE_DB_PATH
TABLE_NAME = "event_cache"

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row # Access columns by name
    return conn

def initialize_cache():
    """
    Initializes the event cache database and table if they don't exist.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_hash TEXT UNIQUE NOT NULL, -- To prevent duplicate entries if re-collected
                    timestamp TEXT NOT NULL,         -- ISO 8601 format, UTC
                    event_type TEXT NOT NULL,        -- e.g., 'window_activity', 'afk'
                    source TEXT NOT NULL,            -- e.g., 'activitywatch'
                    device_id TEXT NOT NULL,
                    data TEXT NOT NULL,              -- JSON string of the event payload
                    added_at TEXT NOT NULL,          -- Timestamp when added to cache
                    send_attempts INTEGER DEFAULT 0,
                    last_send_attempt_at TEXT NULL
                )
            """)
            # Add indexes for faster querying
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_event_hash ON {TABLE_NAME} (event_hash)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_timestamp ON {TABLE_NAME} (timestamp)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_added_at ON {TABLE_NAME} (added_at)")
            conn.commit()
        log.info(f"Event cache initialized successfully at {DB_PATH}")
    except sqlite3.Error as e:
        log.error(f"Error initializing event cache: {e}", exc_info=True)
        raise

def add_event_to_cache(event: Dict[str, Any]) -> bool:
    """
    Adds a single event to the local cache.
    The event dictionary should include:
    - event_hash (str): A unique hash for the event.
    - timestamp (datetime): The original event timestamp (will be stored as ISO string in UTC).
    - event_type (str): Type of the event.
    - source (str): Source of the event.
    - device_id (str): ID of the device generating the event.
    - data (dict): The actual event payload.

    Returns True if the event was added, False if it was a duplicate or an error occurred.
    """
    if not all(k in event for k in ["event_hash", "timestamp", "event_type", "source", "device_id", "data"]):
        log.error(f"Event missing required keys: {event.keys()}")
        return False

    now_utc_iso = datetime.now(timezone.utc).isoformat()
    event_timestamp_iso = event["timestamp"].isoformat() if isinstance(event["timestamp"], datetime) else event["timestamp"]

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                INSERT INTO {TABLE_NAME} (event_hash, timestamp, event_type, source, device_id, data, added_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                event["event_hash"],
                event_timestamp_iso,
                event["event_type"],
                event["source"],
                event["device_id"],
                json.dumps(event["data"]),
                now_utc_iso
            ))
            conn.commit()
            log.debug(f"Event {event['event_hash']} added to cache.")
            return True
    except sqlite3.IntegrityError:
        log.debug(f"Event {event['event_hash']} already exists in cache. Skipping.")
        return False
    except sqlite3.Error as e:
        log.error(f"Error adding event {event.get('event_hash', 'N/A')} to cache: {e}", exc_info=True)
        return False
    except json.JSONDecodeError as e:
        log.error(f"Error serializing event data for {event.get('event_hash', 'N/A')}: {e}", exc_info=True)
        return False

def get_batched_events(limit: int = config.MAX_BATCH_SIZE) -> List[Dict[str, Any]]:
    """
    Retrieves a batch of events from the cache, prioritizing older ones.
    Marks them as attempted.
    """
    events_to_send = []
    ids_to_update = []
    now_utc_iso = datetime.now(timezone.utc).isoformat()

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Select events that haven't been attempted too many times
            # Prioritize older events (by added_at)
            cursor.execute(f"""
                SELECT id, event_hash, timestamp, event_type, source, device_id, data, send_attempts
                FROM {TABLE_NAME}
                ORDER BY added_at ASC
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            if not rows:
                return []

            for row in rows:
                try:
                    event_data = json.loads(row["data"])
                    events_to_send.append({
                        "cache_id": row["id"], # Internal ID for deletion/update
                        "event_hash": row["event_hash"],
                        "timestamp": row["timestamp"], # Already ISO string
                        "event_type": row["event_type"],
                        "source": row["source"],
                        "device_id": row["device_id"],
                        "data": event_data
                    })
                    ids_to_update.append(row["id"])
                except json.JSONDecodeError as e:
                    log.error(f"Error decoding JSON for event ID {row['id']} from cache: {e}")
                    # Potentially mark this event as problematic or skip
                    continue
            
            if ids_to_update:
                # Mark these events as having an attempt
                update_query = f"""
                    UPDATE {TABLE_NAME}
                    SET send_attempts = send_attempts + 1,
                        last_send_attempt_at = ?
                    WHERE id IN ({','.join('?' for _ in ids_to_update)})
                """
                cursor.execute(update_query, [now_utc_iso] + ids_to_update)
                conn.commit()
                log.info(f"Retrieved {len(events_to_send)} events for batching. Marked {len(ids_to_update)} events as attempted.")

    except sqlite3.Error as e:
        log.error(f"Error retrieving batched events: {e}", exc_info=True)
        return [] # Return empty list on error to prevent processing partial/stale data
    
    return events_to_send

def delete_events_from_cache(event_cache_ids: List[int]) -> bool:
    """
    Deletes events from the cache by their internal cache IDs.
    Typically called after successful transmission to the server.
    """
    if not event_cache_ids:
        return True # Nothing to delete

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' for _ in event_cache_ids)
            cursor.execute(f"DELETE FROM {TABLE_NAME} WHERE id IN ({placeholders})", event_cache_ids)
            conn.commit()
            log.info(f"Successfully deleted {cursor.rowcount} events from cache with IDs: {event_cache_ids}")
            return True
    except sqlite3.Error as e:
        log.error(f"Error deleting events from cache: {e}", exc_info=True)
        return False

def get_cache_size() -> int:
    """Returns the total number of events currently in the cache."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(id) FROM {TABLE_NAME}")
            count = cursor.fetchone()[0]
            return count if count is not None else 0
    except sqlite3.Error as e:
        log.error(f"Error getting cache size: {e}", exc_info=True)
        return -1 # Indicate error

# Initialize the cache when this module is loaded
if __name__ != "__main__": # Avoid running during direct script execution for testing
    initialize_cache()
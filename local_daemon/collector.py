"""
Data Collector for the Local Daemon.
Focuses on collecting events from ActivityWatch.
"""
import logging
import time
import hashlib
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple

from aw_client import ActivityWatchClient
from aw_core.models import Event as AWEvent

from . import config
from . import cache

log = logging.getLogger(__name__)

# Constants adapted from backend/app/ingestion/activitywatch.py
# For hash generation
TIMESTAMP_PREFIX = "ts:"
APP_PREFIX = "|app:"
TITLE_PREFIX = "|title:"
URL_PREFIX = "|url:"
EMPTY_STRING = ""
MILLISECONDS_MULTIPLIER = 1000

# Event types
EVENT_TYPE_WINDOW = "desktop_activity.window"
EVENT_TYPE_AFK = "desktop_activity.afk"
EVENT_TYPE_WEB = "browser_activity.web" # Generic, actual might depend on browser extension

class ActivityWatchCollector:
    """Collects data from ActivityWatch."""

    def __init__(self):
        self.client_name = config.AW_CLIENT_NAME
        try:
            self.aw_client = ActivityWatchClient(client_name=self.client_name, testing=False)
            log.info(f"ActivityWatch client '{self.client_name}' initialized.")
        except Exception as e:
            log.error(f"Failed to initialize ActivityWatch client: {e}", exc_info=True)
            self.aw_client = None # Ensure client is None if initialization fails

        self.last_collection_times: Dict[str, Optional[datetime]] = {
            config.AW_WINDOW_BUCKET_ID: None,
            config.AW_AFK_BUCKET_ID: None,
            config.AW_WEB_BROWSER_BUCKET_ID: None,
        }
        # A small overlap to ensure no events are missed between runs
        self.collection_overlap = timedelta(seconds=30)


    def _generate_event_hash(self, timestamp: datetime, app: str, title: str, url: Optional[str]) -> str:
        """
        Generates a stable SHA-256 hash for an event to allow for deduplication.
        Adapted from HashGenerator in backend/app/ingestion/activitywatch.py
        """
        if not timestamp: # Should always have a timestamp
            timestamp_utc_millis_str = EMPTY_STRING
        else:
            timestamp_utc = timestamp.astimezone(timezone.utc)
            timestamp_millis = int(timestamp_utc.timestamp() * MILLISECONDS_MULTIPLIER)
            timestamp_utc_millis_str = str(timestamp_millis)

        payload_string = (
            f"{TIMESTAMP_PREFIX}{timestamp_utc_millis_str}"
            f"{APP_PREFIX}{app or EMPTY_STRING}"
            f"{TITLE_PREFIX}{title or EMPTY_STRING}"
            f"{URL_PREFIX}{url or EMPTY_STRING}"
        )
        return hashlib.sha256(payload_string.encode("utf-8")).hexdigest()

    def _fetch_events_from_bucket(self, bucket_id: str, start_time: datetime, end_time: datetime) -> List[AWEvent]:
        """Fetches events from a specific ActivityWatch bucket within a time range."""
        if not self.aw_client:
            log.warning("ActivityWatch client not available. Skipping fetch.")
            return []
        try:
            log.debug(f"Fetching events for bucket '{bucket_id}' from {start_time.isoformat()} to {end_time.isoformat()}")
            events = self.aw_client.get_events(
                bucket_id=bucket_id,
                start=start_time,
                end=end_time,
                limit=-1  # Get all events in the range
            )
            log.info(f"Fetched {len(events)} events from bucket '{bucket_id}'.")
            return events
        except Exception as e:
            log.error(f"Error fetching events from bucket '{bucket_id}': {e}", exc_info=True)
            return []

    def _process_aw_event(self, aw_event: AWEvent, bucket_type: str, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Transforms a raw ActivityWatch event into the desired cache format.
        Performs minimal local processing (e.g., filtering duplicates via hash).
        """
        timestamp = aw_event.timestamp.replace(tzinfo=timezone.utc)
        duration_seconds = aw_event.duration.total_seconds()

        if duration_seconds < config.AW_MIN_DURATION_SECONDS and bucket_type != EVENT_TYPE_AFK: # AFK events are kept regardless of duration
            log.debug(f"Skipping event due to short duration ({duration_seconds}s): {aw_event.data.get('title', aw_event.data.get('status'))}")
            return None

        app = aw_event.data.get("app")
        title = aw_event.data.get("title")
        url = aw_event.data.get("url") # Mainly for web events

        # For AFK events, app/title might be structured differently
        if bucket_type == EVENT_TYPE_AFK:
            status = aw_event.data.get("status", "unknown_afk_status")
            app = "AFK" # Standardize app name for AFK events
            title = status # Use AFK status (e.g., "not-afk", "afk") as title

        event_hash = self._generate_event_hash(
            timestamp,
            app or EMPTY_STRING,
            title or EMPTY_STRING,
            url or EMPTY_STRING
        )

        processed_event = {
            "event_hash": event_hash,
            "timestamp": timestamp, # datetime object
            "event_type": bucket_type,
            "source": "activitywatch",
            "device_id": device_id,
            "data": {
                "app": app,
                "title": title,
                "url": url,
                "duration_seconds": duration_seconds,
                # Add any other relevant fields from aw_event.data if needed
            }
        }
        return processed_event

    def collect_and_store_events(self):
        """
        Main collection loop. Fetches new events from configured AW buckets
        and stores them in the local cache.
        """
        if not self.aw_client:
            log.warning("ActivityWatch client not initialized. Cannot collect events.")
            return 0

        collected_count = 0
        now_utc = datetime.now(timezone.utc)
        device_id = config.DEVICE_ID # Get device ID from config

        bucket_map = {
            config.AW_WINDOW_BUCKET_ID: EVENT_TYPE_WINDOW,
            config.AW_AFK_BUCKET_ID: EVENT_TYPE_AFK,
            config.AW_WEB_BROWSER_BUCKET_ID: EVENT_TYPE_WEB,
        }

        for bucket_id, event_type_prefix in bucket_map.items():
            if not bucket_id: # Skip if bucket_id is not configured
                log.warning(f"Bucket ID for {event_type_prefix} not configured. Skipping.")
                continue

            last_ts = self.last_collection_times.get(bucket_id)
            if last_ts:
                start_time = last_ts - self.collection_overlap
            else:
                # On first run for a bucket, go back a defined period (e.g., collection interval)
                # Or make it configurable, for now, let's use the collection interval
                start_time = now_utc - timedelta(seconds=config.COLLECTION_INTERVAL_SECONDS) - self.collection_overlap
            
            end_time = now_utc # Collect up to the current time

            log.info(f"Attempting collection for bucket: {bucket_id} ({event_type_prefix})")
            raw_aw_events = self._fetch_events_from_bucket(bucket_id, start_time, end_time)

            if not raw_aw_events:
                log.debug(f"No new events from {bucket_id} for period {start_time.isoformat()} to {end_time.isoformat()}")
                self.last_collection_times[bucket_id] = end_time # Update last collection time even if no events
                continue

            # Minimal processing: remove exact duplicate consecutive events (based on data, not hash yet)
            # This is a simple filter; more complex filtering can be added.
            # For now, we rely on the event_hash for deduplication in the cache.
            
            new_events_for_bucket = 0
            for aw_event in raw_aw_events:
                processed_event = self._process_aw_event(aw_event, event_type_prefix, device_id)
                if processed_event:
                    if cache.add_event_to_cache(processed_event):
                        collected_count += 1
                        new_events_for_bucket +=1
            
            if new_events_for_bucket > 0:
                log.info(f"Added {new_events_for_bucket} new events from {bucket_id} to cache.")

            # Update the last collection timestamp for this bucket to the end_time of this run
            self.last_collection_times[bucket_id] = end_time
        
        if collected_count > 0:
            log.info(f"Total new events collected and added to cache in this run: {collected_count}")
        else:
            log.info("No new events collected in this run.")
        
        return collected_count

    def collect_all_events(self, start_time: datetime, end_time: datetime) -> list:
        """
        Collects and processes all ActivityWatch events from all configured buckets for the given time range.
        Returns a flat list of processed events (ready for sending to server).
        """
        if not self.aw_client:
            log.warning("ActivityWatch client not initialized. Cannot collect events.")
            return []

        device_id = config.DEVICE_ID
        bucket_map = {
            config.AW_WINDOW_BUCKET_ID: EVENT_TYPE_WINDOW,
            config.AW_AFK_BUCKET_ID: EVENT_TYPE_AFK,
            config.AW_WEB_BROWSER_BUCKET_ID: EVENT_TYPE_WEB,
        }
        all_events = []
        for bucket_id, event_type_prefix in bucket_map.items():
            if not bucket_id:
                log.warning(f"Bucket ID for {event_type_prefix} not configured. Skipping.")
                continue
            raw_aw_events = self._fetch_events_from_bucket(bucket_id, start_time, end_time)
            for aw_event in raw_aw_events:
                processed_event = self._process_aw_event(aw_event, event_type_prefix, device_id)
                if processed_event:
                    all_events.append(processed_event)
        return all_events


if __name__ == '__main__':
    # Basic test for the collector
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s")
    
    # Ensure cache is initialized for testing if run directly
    try:
        cache.initialize_cache() 
    except Exception as e:
        log.error(f"Failed to initialize cache for testing: {e}")
        exit(1)

    collector = ActivityWatchCollector()
    if collector.aw_client: # Proceed only if client initialized
        log.info("Running manual collection test...")
        events_collected = collector.collect_and_store_events()
        log.info(f"Manual collection test finished. Events collected: {events_collected}")
        cache_size = cache.get_cache_size()
        log.info(f"Current cache size: {cache_size}")
    else:
        log.error("AW Client not available, skipping manual collection test.")

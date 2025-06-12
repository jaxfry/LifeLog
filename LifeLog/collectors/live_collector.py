import time
import threading
import logging
from typing import Optional
from LifeLog.ingestion.activitywatch import fetch_new_events
from LifeLog.database import get_connection
from LifeLog.config import Settings

class LiveCollector:
    def __init__(self, polling_interval: Optional[int] = None, retry_attempts: Optional[int] = None, retry_delay: Optional[int] = None):
        settings = Settings()
        self.polling_interval = polling_interval or settings.polling_interval_minutes
        self.retry_attempts = retry_attempts or settings.retry_attempts
        self.retry_delay = retry_delay or settings.retry_delay_seconds
        self._stop_event = threading.Event()
        self.logger = logging.getLogger("LiveCollector")

    def start(self):
        self.logger.info("Starting LiveCollector with interval %d min", self.polling_interval)
        while not self._stop_event.is_set():
            for attempt in range(self.retry_attempts):
                try:
                    self.collect()
                    break
                except Exception as e:
                    self.logger.error(f"Collection failed (attempt {attempt+1}/{self.retry_attempts}): {e}")
                    time.sleep(self.retry_delay)
            time.sleep(self.polling_interval * 60)

    def stop(self):
        self.logger.info("Stopping LiveCollector...")
        self._stop_event.set()

    def collect(self):
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("BEGIN TRANSACTION;")
            last_ts = self._get_last_processed_timestamp(cur)
            new_events = fetch_new_events(since=last_ts)
            if new_events:
                self._insert_events(cur, new_events)
                self._update_last_processed_timestamp(cur, new_events)
            conn.commit()
            self.logger.info(f"Collected {len(new_events)} new events.")

    def _get_last_processed_timestamp(self, cur):
        cur.execute("SELECT value FROM metadata WHERE key = 'last_processed_timestamp'")
        row = cur.fetchone()
        return row[0] if row else None

    def _insert_events(self, cur, events):
        import uuid
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        for event in events:
            # Map event fields to DB columns
            event_id = str(uuid.uuid4())
            start_time = datetime.fromtimestamp(event["timestamp"] / 1000, tz=timezone.utc)
            end_time = start_time + timedelta(milliseconds=event["duration_ms"] or 0)
            duration_s = int((event["duration_ms"] or 0) / 1000)
            source = "activitywatch"
            app_name = event.get("app")
            window_title = event.get("title")
            category = None
            notes = None
            last_modified = now
            cur.execute(
                """
                INSERT INTO timeline_events (event_id, start_time, end_time, duration_s, source, app_name, window_title, category, notes, last_modified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, start_time, end_time, duration_s, source, app_name, window_title, category, notes, last_modified)
            )

    def _update_last_processed_timestamp(self, cur, events):
        max_ts = max(e['timestamp'] for e in events)
        cur.execute("INSERT INTO metadata (key, value) VALUES ('last_processed_timestamp', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(max_ts),))

# Graceful shutdown handler and CLI integration will be added separately.

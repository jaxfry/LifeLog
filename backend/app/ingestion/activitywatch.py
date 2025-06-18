import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple, Union, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod

import polars as pl
from aw_client import ActivityWatchClient
from aw_core.models import Event as AWEvent
import duckdb

from backend.app.core.settings import Settings

log = logging.getLogger(__name__)

# Constants - extracted to improve readability and maintainability
RAW_EVENT_SCHEMA = ["timestamp", "duration", "app", "title", "url"]
ACTIVE_STATUS = "not-afk"
AFK_APP_NAME = "AFK"
DIGITAL_ACTIVITY_EVENT_TYPE = "digital_activity"
ACTIVITYWATCH_SOURCE = "activitywatch"
PENDING_STATUS = "pending"

@dataclass
class BucketInfo:
    """Value object to encapsulate bucket information."""
    bucket_id: str
    bucket_type: str

# ==============================================================================
# 1. ABSTRACTIONS AND INTERFACES
# ==============================================================================

class EventProcessor(ABC):
    """Abstract base class for processing different types of events."""
    
    @abstractmethod
    def process(self, *args, **kwargs) -> Any:
        """Process events and return the processed result."""
        pass


class DataValidator:
    """Validates and normalizes event data."""
    
    @staticmethod
    def ensure_schema_compliance(df: pl.DataFrame, bucket_type: str) -> pl.DataFrame:
        """Ensures DataFrame has all required columns with proper types."""
        if df.is_empty():
            return pl.DataFrame(schema={col: pl.Utf8 for col in RAW_EVENT_SCHEMA})
        
        # Add missing columns
        for col in RAW_EVENT_SCHEMA:
            if col not in df.columns:
                df = df.with_columns(pl.lit(None, dtype=pl.Utf8).alias(col))
        
        # Handle special bucket types
        if bucket_type == "afk" and "status" in df.columns:
            df = df.with_columns(
                pl.lit(AFK_APP_NAME).alias("app"),
                pl.col("status").alias("title")
            )
        
        return df.select(RAW_EVENT_SCHEMA)


class HashGenerator:
    """Generates stable hashes for event identification."""
    
    @staticmethod
    def generate_payload_hash(row: dict) -> str:
        """Generates a stable SHA-256 hash unique per event slice."""
        timestamp = row.get("start_time")
        timestamp_bucket = ""
        
        if timestamp:
            timestamp_bucket = str(int(timestamp.astimezone(timezone.utc).timestamp() * 1000))
        
        payload = (
            f"ts:{timestamp_bucket}"
            f"|app:{row.get('app') or ''}"
            f"|title:{row.get('title') or ''}"
            f"|url:{row.get('url') or ''}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ==============================================================================
# 2. DATA FETCHING LAYER
# ==============================================================================

class ActivityWatchDataFetcher:
    """Handles fetching data from ActivityWatch buckets."""
    
    def __init__(self, client: ActivityWatchClient):
        self.client = client
        self.validator = DataValidator()
    
    async def fetch_all_buckets(
        self, 
        settings: Settings, 
        start: datetime, 
        end: datetime
    ) -> Tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        """Fetches data from all required ActivityWatch buckets concurrently."""
        buckets = [
            BucketInfo(settings.AW_WINDOW_BUCKET, "window"),
            BucketInfo(settings.AW_AFK_BUCKET, "afk"),
            BucketInfo(settings.AW_WEB_BUCKET, "web"),
        ]
        
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor() as executor:
            tasks = [
                self._fetch_single_bucket(loop, executor, bucket, start, end)
                for bucket in buckets
            ]
            results = await asyncio.gather(*tasks)
        
        df_window, df_afk, df_web = results
        log.info(f"Fetched {df_window.height} window, {df_afk.height} AFK, and {df_web.height} web events.")
        return df_window, df_afk, df_web
    
    async def _fetch_single_bucket(
        self, 
        loop, 
        executor, 
        bucket_info: BucketInfo, 
        start: datetime, 
        end: datetime
    ) -> pl.DataFrame:
        """Fetches and processes events from a single bucket."""
        def _fetch_events():
            try:
                return self.client.get_events(
                    bucket_id=bucket_info.bucket_id, 
                    start=start, 
                    end=end, 
                    limit=-1
                )
            except Exception as e:
                log.warning(f"Could not fetch data for bucket '{bucket_info.bucket_id}'. Error: {e}")
                return []
        
        events = await loop.run_in_executor(executor, _fetch_events)
        return self._convert_events_to_dataframe(events, bucket_info.bucket_type)
    
    def _convert_events_to_dataframe(self, events: List[AWEvent], bucket_type: str) -> pl.DataFrame:
        """Converts ActivityWatch events to a normalized DataFrame."""
        if not events:
            return pl.DataFrame(schema={col: pl.Utf8 for col in RAW_EVENT_SCHEMA})
        
        records = [
            {"timestamp": event.timestamp, "duration": event.duration, **event.data} 
            for event in events
        ]
        df = pl.from_dicts(records)
        return self.validator.ensure_schema_compliance(df, bucket_type)

# ==============================================================================
# 3. EVENT PROCESSING LAYER
# ==============================================================================

class AfkEventProcessor(EventProcessor):
    """Processes AFK (Away From Keyboard) events."""
    
    def process(
        self, 
        df_afk_raw: pl.DataFrame, 
        start_utc: datetime, 
        end_utc: datetime
    ) -> Tuple[pl.DataFrame, pl.DataFrame]:
        """Processes raw AFK events into consolidated blocks and active intervals."""
        if df_afk_raw.is_empty():
            log.warning("No AFK data found, assuming entire window is 'active'.")
            df_active_intervals = pl.DataFrame({"start": [start_utc], "end": [end_utc]})
            empty_afk = pl.DataFrame(schema={
                "start_time": pl.Datetime, 
                "end_time": pl.Datetime, 
                "app": pl.Utf8, 
                "title": pl.Utf8
            })
            return empty_afk, df_active_intervals
        
        df_afk_consolidated = self._consolidate_afk_blocks(df_afk_raw)
        df_active_intervals = self._extract_active_intervals(df_afk_consolidated)
        
        return df_afk_consolidated, df_active_intervals
    
    def _consolidate_afk_blocks(self, df_afk_raw: pl.DataFrame) -> pl.DataFrame:
        """Consolidates consecutive AFK events of the same type."""
        df_sorted = df_afk_raw.sort("timestamp")
        
        df_grouped = df_sorted.with_columns(
            pl.col("title").rle_id().alias("state_group")
        ).group_by("app", "title", "state_group").agg(
            pl.col("timestamp").min().alias("start_time"),
            (pl.col("timestamp").max() + pl.col("duration").max()).alias("end_time")
        ).sort("start_time")
        
        return df_grouped.select("start_time", "end_time", "app", "title")
    
    def _extract_active_intervals(self, df_afk_consolidated: pl.DataFrame) -> pl.DataFrame:
        """Extracts time intervals when the user was active (not AFK)."""
        return df_afk_consolidated.filter(
            pl.col("title") == ACTIVE_STATUS
        ).rename({
            "start_time": "start", 
            "end_time": "end"
        }).select("start", "end")


class ActivityEventProcessor(EventProcessor):
    """Processes window and web activity events."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
    
    def process(
        self,
        df_window: pl.DataFrame,
        df_web: pl.DataFrame,
        df_active_intervals: pl.DataFrame
    ) -> pl.DataFrame:
        """Merges activity data and intersects with active time intervals."""
        df_merged_activity = self._merge_activity_sources(df_window, df_web)
        if df_merged_activity.is_empty():
            log.info("No window or web activity events found to process.")
            return pl.DataFrame()
        
        if df_active_intervals.is_empty():
            log.warning("No active intervals found; returning no activity.")
            return pl.DataFrame()
        
        df_intersected = self._intersect_with_active_time(df_merged_activity, df_active_intervals)
        return self._filter_by_minimum_duration(df_intersected)
    
    def _merge_activity_sources(self, df_window: pl.DataFrame, df_web: pl.DataFrame) -> pl.DataFrame:
        """Combines window and web activity data."""
        df_all_activity = pl.concat([df_window, df_web]).drop_nulls("timestamp")
        
        if df_all_activity.is_empty():
            return df_all_activity
        
        return df_all_activity.with_columns(
            pl.col("timestamp").alias("start_time"),
            (pl.col("timestamp") + pl.col("duration")).alias("end_time")
        ).sort("start_time")
    
    def _intersect_with_active_time(
        self, 
        df_activity: pl.DataFrame, 
        df_active_intervals: pl.DataFrame
    ) -> pl.DataFrame:
        """Intersects activity events with periods when user was active."""
        df_intersected = df_activity.join(
            df_active_intervals, how="cross"
        ).filter(
            (pl.col("start_time") < pl.col("end")) & (pl.col("end_time") > pl.col("start"))
        ).with_columns(
            pl.max_horizontal("start_time", "start").alias("new_start"),
            pl.min_horizontal("end_time", "end").alias("new_end")
        ).select(
            pl.col("new_start").alias("start_time"),
            pl.col("new_end").alias("end_time"),
            "app", "title", "url"
        ).unique()
        
        return df_intersected
    
    def _filter_by_minimum_duration(self, df: pl.DataFrame) -> pl.DataFrame:
        """Filters out events shorter than the minimum duration threshold."""
        if df.is_empty():
            return df
        
        return df.filter(
            (pl.col("end_time") - pl.col("start_time")).dt.total_seconds() > self.settings.AW_MIN_DURATION_S
        )


class DataFrameEnricher:
    """Enriches processed DataFrames with metadata and standardized formats."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.hash_generator = HashGenerator()
    
    def enrich_final_dataframe(
        self, 
        df_activities: pl.DataFrame, 
        df_afk: pl.DataFrame
    ) -> pl.DataFrame:
        """Combines and enriches activity and AFK data with metadata."""
        df_harmonized = self._harmonize_schemas(df_activities, df_afk)
        df_combined = pl.concat([df_harmonized["activities"], df_harmonized["afk"]])
        
        if df_combined.is_empty():
            return df_combined
        
        df_sorted = df_combined.sort("start_time").drop_nulls("start_time")
        return self._add_metadata(df_sorted)
    
    def _harmonize_schemas(self, df_activities: pl.DataFrame, df_afk: pl.DataFrame) -> dict:
        """Ensures both DataFrames have consistent schemas."""
        if not df_afk.is_empty():
            df_afk = df_afk.with_columns(pl.lit(None, dtype=pl.Utf8).alias("url"))
        
        return {"activities": df_activities, "afk": df_afk}
    
    def _add_metadata(self, df: pl.DataFrame) -> pl.DataFrame:
        """Adds required metadata columns for database storage."""
        return df.with_columns(
            pl.struct(["start_time", "app", "title", "url"])
              .map_elements(self.hash_generator.generate_payload_hash, return_dtype=pl.Utf8)
              .alias("payload_hash"),
            pl.lit(DIGITAL_ACTIVITY_EVENT_TYPE).alias("event_type"),
            pl.lit(ACTIVITYWATCH_SOURCE).alias("source"),
            pl.lit(self.settings.AW_HOSTNAME).alias("hostname")
        )

# ==============================================================================
# 4. DATABASE OPERATIONS LAYER
# ==============================================================================

class DatabaseWriter:
    """Handles writing processed events to the database."""
    
    def write_events(self, con: duckdb.DuckDBPyConnection, df_events: pl.DataFrame) -> None:
        """Atomically writes event data to DuckDB."""
        if df_events.is_empty():
            log.info("No events to write to database.")
            return
        
        con.register('df_to_insert', df_events)
        
        try:
            self._insert_events(con)
            self._insert_activity_data(con)
            log.info(f"Successfully wrote {df_events.height} events to database.")
        except Exception as e:
            log.error(f"Error writing events to database: {e}", exc_info=True)
            raise
        finally:
            con.unregister('df_to_insert')
    
    def _insert_events(self, con: duckdb.DuckDBPyConnection) -> None:
        """Inserts events into the main events table."""
        con.execute("""
            INSERT INTO events (id, source, event_type, start_time, end_time, payload_hash, processing_status)
            SELECT gen_random_uuid(), source, event_type::event_kind, start_time, end_time, payload_hash, ?::processing_status_enum
            FROM df_to_insert
            ON CONFLICT (payload_hash) DO NOTHING;
        """, [PENDING_STATUS])
    
    def _insert_activity_data(self, con: duckdb.DuckDBPyConnection) -> None:
        """Inserts digital activity data into the specialized table."""
        con.execute("""
            INSERT INTO digital_activity_data (event_id, hostname, app, title, url)
            SELECT e.id, i.hostname, i.app, i.title, i.url
            FROM df_to_insert AS i
            JOIN events AS e ON i.payload_hash = e.payload_hash
            ON CONFLICT (event_id) DO NOTHING;
        """)


# ==============================================================================
# 5. MAIN ORCHESTRATOR
# ==============================================================================

class ActivityWatchIngestionOrchestrator:
    """Main orchestrator for ActivityWatch data ingestion process."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = ActivityWatchClient("lifelog-ingestor")
        self.fetcher = ActivityWatchDataFetcher(self.client)
        self.afk_processor = AfkEventProcessor()
        self.activity_processor = ActivityEventProcessor(settings)
        self.enricher = DataFrameEnricher(settings)
        self.db_writer = DatabaseWriter()
    
    async def ingest_time_window(
        self, 
        con: duckdb.DuckDBPyConnection, 
        start_utc: datetime, 
        end_utc: datetime
    ) -> None:
        """Orchestrates the complete ingestion process for a time window."""
        log.info(f"Starting ActivityWatch ingestion for window: {start_utc} -> {end_utc}")
        
        try:
            # Step 1: Fetch raw data
            df_window_raw, df_afk_raw, df_web_raw = await self.fetcher.fetch_all_buckets(
                self.settings, start_utc, end_utc
            )
            
            if df_window_raw.is_empty() and df_afk_raw.is_empty():
                log.info("No window or AFK events found in the time range. Nothing to do.")
                return
            
            # Step 2: Process AFK events to get active intervals
            df_afk_final, df_active_intervals = self.afk_processor.process(
                df_afk_raw, start_utc, end_utc
            )
            
            # Step 3: Process activity events
            df_activities_final = self.activity_processor.process(
                df_window_raw, df_web_raw, df_active_intervals
            )
            
            # Step 4: Enrich and combine all data
            df_to_ingest = self.enricher.enrich_final_dataframe(df_activities_final, df_afk_final)
            
            # Step 5: Write to database
            if not df_to_ingest.is_empty():
                self.db_writer.write_events(con, df_to_ingest)
                log.info(f"Successfully completed ActivityWatch ingestion for window: {start_utc} -> {end_utc}")
            else:
                log.info("No events to ingest after processing.")
                
        except Exception as e:
            log.error(f"Failed to ingest ActivityWatch data: {e}", exc_info=True)
            raise


# ==============================================================================
# 6. PUBLIC API FUNCTIONS (LEGACY COMPATIBILITY)
# ==============================================================================

def ingest_activitywatch_data(
    con: duckdb.DuckDBPyConnection, 
    settings: Settings, 
    start_utc: datetime, 
    end_utc: datetime
) -> None:
    """
    Legacy function maintained for backward compatibility.
    Delegates to the new orchestrator implementation.
    """
    async def main():
        orchestrator = ActivityWatchIngestionOrchestrator(settings)
        await orchestrator.ingest_time_window(con, start_utc, end_utc)
    
    asyncio.run(main())


def ingest_aw_window(
    con: duckdb.DuckDBPyConnection, 
    settings: Settings, 
    start_utc: datetime, 
    end_utc: datetime
) -> None:
    """
    Legacy function maintained for backward compatibility.
    Ingests ActivityWatch data for the specified time window.
    """
    log.info(f"Ingesting ActivityWatch data from {start_utc} to {end_utc}")
    ingest_activitywatch_data(con, settings, start_utc, end_utc)

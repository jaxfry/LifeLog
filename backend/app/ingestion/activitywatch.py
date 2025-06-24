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
from backend.app.core.utils import with_db_write_retry

log = logging.getLogger(__name__)

# Constants - extracted to improve readability and maintainability
RAW_EVENT_SCHEMA = ["timestamp", "duration", "app", "title", "url"]
REQUIRED_EVENT_COLUMNS = ["start_time", "end_time", "app", "title", "url"]
ACTIVE_STATUS = "not-afk"
AFK_APP_NAME = "AFK"
DIGITAL_ACTIVITY_EVENT_TYPE = "digital_activity"
ACTIVITYWATCH_SOURCE = "activitywatch"
PENDING_STATUS = "pending"

# Database operation constants
MILLISECONDS_MULTIPLIER = 1000
EMPTY_STRING = ""
STATUS_COLUMN = "status"

# Bucket type identifiers
AFK_BUCKET_TYPE = "afk"
WINDOW_BUCKET_TYPE = "window"
WEB_BUCKET_TYPE = "web"

# Hash generation components
TIMESTAMP_PREFIX = "ts:"
APP_PREFIX = "|app:"
TITLE_PREFIX = "|title:"
URL_PREFIX = "|url:"

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
            return DataValidator._create_empty_schema_dataframe()
        
        df = DataValidator._add_missing_columns(df)
        df = DataValidator._handle_special_bucket_types(df, bucket_type)
        
        return df.select(RAW_EVENT_SCHEMA)
    
    @staticmethod
    def _create_empty_schema_dataframe() -> pl.DataFrame:
        """Creates an empty DataFrame with the correct schema."""
        return pl.DataFrame(schema={col: pl.Utf8 for col in RAW_EVENT_SCHEMA})
    
    @staticmethod
    def _add_missing_columns(df: pl.DataFrame) -> pl.DataFrame:
        """Adds any missing required columns to the DataFrame."""
        for column_name in RAW_EVENT_SCHEMA:
            if column_name not in df.columns:
                df = df.with_columns(pl.lit(None, dtype=pl.Utf8).alias(column_name))
        return df
    
    @staticmethod
    def _handle_special_bucket_types(df: pl.DataFrame, bucket_type: str) -> pl.DataFrame:
        """Handles special processing for specific bucket types."""
        if bucket_type == AFK_BUCKET_TYPE and STATUS_COLUMN in df.columns:
            df = df.with_columns(
                pl.lit(AFK_APP_NAME).alias("app"),
                pl.col(STATUS_COLUMN).alias("title")
            )
        return df


class HashGenerator:
    """Generates stable hashes for event identification."""
    
    @staticmethod
    def generate_payload_hash(row: dict) -> str:
        """Generates a stable SHA-256 hash unique per event slice."""
        timestamp_bucket = HashGenerator._extract_timestamp_bucket(row)
        payload_components = HashGenerator._build_payload_components(row, timestamp_bucket)
        payload_string = HashGenerator._combine_payload_components(payload_components)
        
        return hashlib.sha256(payload_string.encode("utf-8")).hexdigest()
    
    @staticmethod
    def _extract_timestamp_bucket(row: dict) -> str:
        """Extracts and formats timestamp for hash generation."""
        timestamp = row.get("start_time")
        if not timestamp:
            return EMPTY_STRING
        
        timestamp_utc = timestamp.astimezone(timezone.utc)
        timestamp_millis = int(timestamp_utc.timestamp() * MILLISECONDS_MULTIPLIER)
        return str(timestamp_millis)
    
    @staticmethod
    def _build_payload_components(row: dict, timestamp_bucket: str) -> dict:
        """Builds the individual components for the payload hash."""
        return {
            "timestamp": timestamp_bucket,
            "app": row.get("app", EMPTY_STRING),
            "title": row.get("title", EMPTY_STRING),
            "url": row.get("url", EMPTY_STRING)
        }
    
    @staticmethod
    def _combine_payload_components(components: dict) -> str:
        """Combines payload components into a single string for hashing."""
        return (
            f"{TIMESTAMP_PREFIX}{components['timestamp']}"
            f"{APP_PREFIX}{components['app']}"
            f"{TITLE_PREFIX}{components['title']}"
            f"{URL_PREFIX}{components['url']}"
        )


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
        bucket_configs = self._create_bucket_configurations(settings)
        
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor() as executor:
            fetch_tasks = [
                self._fetch_single_bucket(loop, executor, bucket, start, end)
                for bucket in bucket_configs
            ]
            results = await asyncio.gather(*fetch_tasks)
        
        df_window, df_afk, df_web = results
        self._log_fetch_results(df_window, df_afk, df_web)
        return df_window, df_afk, df_web
    
    def _create_bucket_configurations(self, settings: Settings) -> List[BucketInfo]:
        """Creates bucket configuration objects for data fetching."""
        return [
            BucketInfo(settings.AW_WINDOW_BUCKET, WINDOW_BUCKET_TYPE),
            BucketInfo(settings.AW_AFK_BUCKET, AFK_BUCKET_TYPE),
            BucketInfo(settings.AW_WEB_BUCKET, WEB_BUCKET_TYPE),
        ]
    
    def _log_fetch_results(self, df_window: pl.DataFrame, df_afk: pl.DataFrame, df_web: pl.DataFrame) -> None:
        """Logs the results of bucket data fetching."""
        log.info(
            f"Successfully fetched ActivityWatch data: "
            f"{df_window.height} window events, "
            f"{df_afk.height} AFK events, "
            f"{df_web.height} web events"
        )
    
    async def _fetch_single_bucket(
        self, 
        loop, 
        executor, 
        bucket_info: BucketInfo, 
        start: datetime, 
        end: datetime
    ) -> pl.DataFrame:
        """Fetches and processes events from a single bucket."""
        def _fetch_events_from_bucket():
            try:
                return self.client.get_events(
                    bucket_id=bucket_info.bucket_id, 
                    start=start, 
                    end=end, 
                    limit=-1
                )
            except Exception as e:
                log.warning(
                    f"Failed to fetch data from bucket '{bucket_info.bucket_id}': {e}. "
                    f"Returning empty result."
                )
                return []
        
        events = await loop.run_in_executor(executor, _fetch_events_from_bucket)
        return self._convert_events_to_dataframe(events, bucket_info.bucket_type)
    
    def _convert_events_to_dataframe(self, events: List[AWEvent], bucket_type: str) -> pl.DataFrame:
        """Converts ActivityWatch events to a normalized DataFrame."""
        if not events:
            return self.validator.ensure_schema_compliance(pl.DataFrame(), bucket_type)
        
        event_records = self._extract_event_records(events)
        events_dataframe = pl.from_dicts(event_records)
        return self.validator.ensure_schema_compliance(events_dataframe, bucket_type)
    
    def _extract_event_records(self, events: List[AWEvent]) -> List[dict]:
        """Extracts record dictionaries from ActivityWatch events."""
        return [
            {
                "timestamp": event.timestamp, 
                "duration": event.duration, 
                **event.data
            } 
            for event in events
        ]

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
            return self._handle_empty_afk_data(start_utc, end_utc)
        
        df_afk_consolidated = self._consolidate_afk_blocks(df_afk_raw)
        df_active_intervals = self._extract_active_intervals(df_afk_consolidated)
        
        return df_afk_consolidated, df_active_intervals
    
    def _handle_empty_afk_data(self, start_utc: datetime, end_utc: datetime) -> Tuple[pl.DataFrame, pl.DataFrame]:
        """Handles the case when no AFK data is available."""
        log.warning("No AFK data found. Assuming entire time window is active.")
        
        df_active_intervals = pl.DataFrame({
            "start": [start_utc], 
            "end": [end_utc]
        })
        
        empty_afk_schema = {
            "start_time": pl.Datetime, 
            "end_time": pl.Datetime, 
            "app": pl.Utf8, 
            "title": pl.Utf8
        }
        empty_afk_dataframe = pl.DataFrame(schema=empty_afk_schema)
        
        return empty_afk_dataframe, df_active_intervals
    
    def _consolidate_afk_blocks(self, df_afk_raw: pl.DataFrame) -> pl.DataFrame:
        """Consolidates consecutive AFK events of the same type."""
        df_sorted = df_afk_raw.sort("timestamp")
        
        df_with_groups = df_sorted.with_columns(
            pl.col("title").rle_id().alias("state_group")
        )
        
        df_consolidated = df_with_groups.group_by("app", "title", "state_group").agg(
            pl.col("timestamp").min().alias("start_time"),
            (pl.col("timestamp").max() + pl.col("duration").max()).alias("end_time")
        ).sort("start_time")
        
        return df_consolidated.select(REQUIRED_EVENT_COLUMNS[:4])  # start_time, end_time, app, title
    
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
            log.warning("No active intervals found. No activity data will be returned.")
            return pl.DataFrame()
        
        df_intersected = self._intersect_with_active_time(df_merged_activity, df_active_intervals)
        return self._filter_by_minimum_duration(df_intersected)
    
    def _merge_activity_sources(self, df_window: pl.DataFrame, df_web: pl.DataFrame) -> pl.DataFrame:
        """Combines window and web activity data."""
        df_combined_activity = pl.concat([df_window, df_web]).drop_nulls("timestamp")
        
        if df_combined_activity.is_empty():
            return df_combined_activity
        
        return self._add_time_boundaries(df_combined_activity)
    
    def _add_time_boundaries(self, df: pl.DataFrame) -> pl.DataFrame:
        """Adds start_time and end_time columns based on timestamp and duration."""
        return df.with_columns(
            pl.col("timestamp").alias("start_time"),
            (pl.col("timestamp") + pl.col("duration")).alias("end_time")
        ).sort("start_time")
    
    def _intersect_with_active_time(
        self, 
        df_activity: pl.DataFrame, 
        df_active_intervals: pl.DataFrame
    ) -> pl.DataFrame:
        """Intersects activity events with periods when user was active."""
        df_cross_joined = df_activity.join(df_active_intervals, how="cross")
        
        df_filtered = df_cross_joined.filter(
            self._create_time_overlap_filter()
        )
        
        df_with_intersected_times = df_filtered.with_columns(
            pl.max_horizontal("start_time", "start").alias("intersected_start"),
            pl.min_horizontal("end_time", "end").alias("intersected_end")
        )
        
        return df_with_intersected_times.select(
            pl.col("intersected_start").alias("start_time"),
            pl.col("intersected_end").alias("end_time"),
            "app", "title", "url"
        ).unique()
    
    def _create_time_overlap_filter(self) -> pl.Expr:
        """Creates a filter expression for time overlap detection."""
        return (pl.col("start_time") < pl.col("end")) & (pl.col("end_time") > pl.col("start"))
    
    def _filter_by_minimum_duration(self, df: pl.DataFrame) -> pl.DataFrame:
        """Filters out events shorter than the minimum duration threshold."""
        if df.is_empty():
            return df
        
        duration_filter = self._create_minimum_duration_filter()
        return df.filter(duration_filter)
    
    def _create_minimum_duration_filter(self) -> pl.Expr:
        """Creates a filter expression for minimum duration requirements."""
        event_duration_seconds = (pl.col("end_time") - pl.col("start_time")).dt.total_seconds()
        return event_duration_seconds > self.settings.AW_MIN_DURATION_S


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
        
        df_cleaned = df_combined.sort("start_time").drop_nulls("start_time")
        return self._add_metadata(df_cleaned)
    
    def _harmonize_schemas(self, df_activities: pl.DataFrame, df_afk: pl.DataFrame) -> dict:
        """Ensures both DataFrames have consistent schemas."""
        df_afk_with_url = self._add_url_column_if_needed(df_afk)
        
        return {
            "activities": df_activities, 
            "afk": df_afk_with_url
        }
    
    def _add_url_column_if_needed(self, df_afk: pl.DataFrame) -> pl.DataFrame:
        """Adds URL column to AFK DataFrame if it's not empty."""
        if df_afk.is_empty():
            return df_afk
        
        return df_afk.with_columns(pl.lit(None, dtype=pl.Utf8).alias("url"))
    
    def _add_metadata(self, df: pl.DataFrame) -> pl.DataFrame:
        """Adds required metadata columns for database storage."""
        df_with_hashes = self._add_payload_hashes(df)
        return self._add_standard_metadata(df_with_hashes)
    
    def _add_payload_hashes(self, df: pl.DataFrame) -> pl.DataFrame:
        """Adds payload hash column using event data."""
        hash_struct = pl.struct(REQUIRED_EVENT_COLUMNS)
        return df.with_columns(
            hash_struct.map_elements(
                self.hash_generator.generate_payload_hash, 
                return_dtype=pl.Utf8
            ).alias("payload_hash")
        )
    
    def _add_standard_metadata(self, df: pl.DataFrame) -> pl.DataFrame:
        """Adds standard metadata columns required for database storage."""
        return df.with_columns(
            pl.lit(DIGITAL_ACTIVITY_EVENT_TYPE).alias("event_type"),
            pl.lit(ACTIVITYWATCH_SOURCE).alias("source"),
            pl.lit(self.settings.AW_HOSTNAME).alias("hostname")
        )

# ==============================================================================
# 4. DATABASE OPERATIONS LAYER
# ==============================================================================

class DatabaseWriter:
    """Handles writing processed events to the database."""
    
    @with_db_write_retry()
    def write_events(self, con: duckdb.DuckDBPyConnection, df_events: pl.DataFrame) -> None:
        """Atomically writes event data to DuckDB."""
        if df_events.is_empty():
            log.info("No events to write to database.")
            return
        
        self._register_dataframe_for_insertion(con, df_events)
        
        try:
            self._perform_database_operations(con)
            log.info(f"Successfully wrote {df_events.height} events to database.")
        except Exception as e:
            log.error(f"Database write operation failed: {e}", exc_info=True)
            raise
        finally:
            self._cleanup_registered_dataframe(con)
    
    def _register_dataframe_for_insertion(self, con: duckdb.DuckDBPyConnection, df_events: pl.DataFrame) -> None:
        """Registers the DataFrame with DuckDB for SQL operations."""
        con.register('df_to_insert', df_events)
    
    def _perform_database_operations(self, con: duckdb.DuckDBPyConnection) -> None:
        """Performs the actual database insert operations."""
        self._insert_events(con)
        self._insert_activity_data(con)
    
    def _cleanup_registered_dataframe(self, con: duckdb.DuckDBPyConnection) -> None:
        """Cleans up registered DataFrame from DuckDB."""
        con.unregister('df_to_insert')
    
    def _insert_events(self, con: duckdb.DuckDBPyConnection) -> None:
        """Inserts events into the main events table."""
        con.execute("""
            INSERT INTO events (id, source, event_type, start_time, end_time, payload_hash)
            SELECT gen_random_uuid(), source, event_type::event_kind, start_time, end_time, payload_hash
            FROM df_to_insert
            ON CONFLICT (payload_hash) DO NOTHING;
        """)
    
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
        log.info(f"Starting ActivityWatch ingestion for time window: {start_utc} -> {end_utc}")
        
        try:
            raw_data = await self._fetch_raw_data(start_utc, end_utc)
            
            if self._is_raw_data_empty(raw_data):
                log.info("No raw data found in the specified time range. Ingestion complete.")
                return
            
            processed_data = self._process_raw_data(raw_data, start_utc, end_utc)
            enriched_data = self._enrich_processed_data(processed_data)
            
            if not enriched_data.is_empty():
                self.db_writer.write_events(con, enriched_data)
                log.info(f"ActivityWatch ingestion completed successfully for: {start_utc} -> {end_utc}")
            else:
                log.info("No events to ingest after processing and enrichment.")
                
        except Exception as e:
            log.error(f"ActivityWatch ingestion failed for {start_utc} -> {end_utc}: {e}", exc_info=True)
            raise
    
    async def _fetch_raw_data(self, start_utc: datetime, end_utc: datetime) -> tuple:
        """Fetches raw data from all ActivityWatch buckets."""
        return await self.fetcher.fetch_all_buckets(self.settings, start_utc, end_utc)
    
    def _is_raw_data_empty(self, raw_data: tuple) -> bool:
        """Checks if the fetched raw data contains any events."""
        df_window_raw, df_afk_raw, df_web_raw = raw_data
        return df_window_raw.is_empty() and df_afk_raw.is_empty()
    
    def _process_raw_data(self, raw_data: tuple, start_utc: datetime, end_utc: datetime) -> dict:
        """Processes the raw data through AFK and activity processors."""
        df_window_raw, df_afk_raw, df_web_raw = raw_data
        
        df_afk_final, df_active_intervals = self.afk_processor.process(
            df_afk_raw, start_utc, end_utc
        )
        
        df_activities_final = self.activity_processor.process(
            df_window_raw, df_web_raw, df_active_intervals
        )
        
        return {
            "activities": df_activities_final,
            "afk": df_afk_final
        }
    
    def _enrich_processed_data(self, processed_data: dict) -> pl.DataFrame:
        """Enriches the processed data with metadata."""
        return self.enricher.enrich_final_dataframe(
            processed_data["activities"], 
            processed_data["afk"]
        )


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
    async def run_ingestion():
        orchestrator = ActivityWatchIngestionOrchestrator(settings)
        await orchestrator.ingest_time_window(con, start_utc, end_utc)
    
    asyncio.run(run_ingestion())


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
    log.info(f"Starting ActivityWatch data ingestion: {start_utc} -> {end_utc}")
    ingest_activitywatch_data(con, settings, start_utc, end_utc)

import asyncio
import hashlib
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import List
from datetime import timezone

import polars as pl
from aw_client import ActivityWatchClient
from aw_core.models import Event as AWEvent
import duckdb

from backend.app.core.settings import Settings

log = logging.getLogger(__name__)

# Define a consistent final schema for raw events.
# This helps prevent errors from missing columns.
RAW_EVENT_SCHEMA = ["timestamp", "duration", "app", "title", "url"]

# ==============================================================================
# 1. HELPER & DATA FETCHING FUNCTIONS
# ==============================================================================

def _flatten_events_to_df(events: List[AWEvent], bucket_type: str) -> pl.DataFrame:
    """
    Converts a list of ActivityWatch Event objects into a Polars DataFrame.
    It robustly handles missing keys from different bucket types.
    """
    if not events:
        return pl.DataFrame(schema={col: pl.Utf8 for col in RAW_EVENT_SCHEMA})

    # The **e.data spread is the source of the varying schemas
    records = [{"timestamp": e.timestamp, "duration": e.duration, **e.data} for e in events]
    df = pl.from_dicts(records)

    # --- FIX: Make schema handling robust ---
    # Ensure all expected columns exist, filling with null if they don't.
    for col in RAW_EVENT_SCHEMA:
        if col not in df.columns:
            df = df.with_columns(pl.lit(None, dtype=pl.Utf8).alias(col))

    # For AFK events, standardize the 'app' and 'title' fields.
    if bucket_type == "afk" and "status" in df.columns:
        df = df.with_columns(
            pl.lit("AFK").alias("app"),
            pl.col("status").alias("title")
        )

    # Return the DataFrame with a consistent column order.
    return df.select(RAW_EVENT_SCHEMA)


async def _fetch_bucket(loop, executor, client, bucket_id, start, end, bucket_type):
    """Asynchronously fetches and flattens events from a single AW bucket."""
    def _get_sync():
        try:
            return client.get_events(bucket_id=bucket_id, start=start, end=end, limit=-1)
        except Exception as e:
            log.warning(f"Could not fetch data for bucket '{bucket_id}'. Error: {e}")
            return []

    events = await loop.run_in_executor(executor, _get_sync)
    return _flatten_events_to_df(events, bucket_type)


async def _fetch_data_async(client: ActivityWatchClient, settings: Settings, start: datetime, end: datetime) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Orchestrates the concurrent fetching of all required ActivityWatch data."""
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as executor:
        tasks = [
            _fetch_bucket(loop, executor, client, settings.AW_WINDOW_BUCKET, start, end, "window"),
            _fetch_bucket(loop, executor, client, settings.AW_AFK_BUCKET, start, end, "afk"),
            _fetch_bucket(loop, executor, client, settings.AW_WEB_BUCKET, start, end, "web"),
        ]
        df_window, df_afk, df_web = await asyncio.gather(*tasks)
    log.info(f"Fetched {df_window.height} window, {df_afk.height} AFK, and {df_web.height} web events.")
    return df_window, df_afk, df_web


def _generate_payload_hash(row: dict) -> str:
    """Stable SHA-256 hash that is unique per event slice."""
    ts = row.get("start_time")
    if ts:
        # canonical UTC, millisecond precision
        ts_bucket = str(int(ts.astimezone(timezone.utc).timestamp() * 1000))
    else:
        ts_bucket = ""          # should only happen for AFK blocks without start_time
    payload = (
        f"ts:{ts_bucket}"
        f"|app:{row.get('app') or ''}"
        f"|title:{row.get('title') or ''}"
        f"|url:{row.get('url') or ''}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

# ==============================================================================
# 2. DATA PROCESSING FUNCTIONS
# ==============================================================================

def _process_afk_events(df_afk_raw: pl.DataFrame, start_utc: datetime, end_utc: datetime) -> tuple[pl.DataFrame, pl.DataFrame]:
    """
    Processes raw AFK events to produce consolidated AFK blocks and a DataFrame
    of "active" (not-afk) time intervals.
    """
    if df_afk_raw.is_empty():
        log.warning("No AFK data found, assuming entire window is 'active'.")
        df_active_intervals = pl.DataFrame({"start": [start_utc], "end": [end_utc]})
        df_afk_final = pl.DataFrame(schema={"start_time": pl.Datetime, "end_time": pl.Datetime, "app": pl.Utf8, "title": pl.Utf8})
        return df_afk_final, df_active_intervals

    df_afk_sorted = df_afk_raw.sort("timestamp")
    df_afk_grouped = df_afk_sorted.with_columns(
        pl.col("title").rle_id().alias("state_group")
    ).group_by("app", "title", "state_group").agg(
        pl.col("timestamp").min().alias("start_time"),
        (pl.col("timestamp").max() + pl.col("duration").max()).alias("end_time")
    ).sort("start_time")

    df_afk_final = df_afk_grouped.select("start_time", "end_time", "app", "title")
    df_active_intervals = df_afk_final.filter(pl.col("title") == "not-afk").rename(
        {"start_time": "start", "end_time": "end"}
    ).select("start", "end")

    return df_afk_final, df_active_intervals


def _process_activity_events(
    df_window: pl.DataFrame,
    df_web: pl.DataFrame,
    df_active_intervals: pl.DataFrame,
    settings: Settings
) -> pl.DataFrame:
    """
    Merges window and web data, then intersects the result with active time
    intervals to get true, focused activity events.
    """
    # Combine window and web events. `concat` handles differing schemas gracefully.
    df_all_activity = pl.concat([df_window, df_web]).drop_nulls("timestamp")
    if df_all_activity.is_empty():
        log.info("No window or web activity events found to process.")
        return pl.DataFrame()

    df_merged = df_all_activity.with_columns(
        pl.col("timestamp").alias("start_time"),
        (pl.col("timestamp") + pl.col("duration")).alias("end_time")
    ).sort("start_time")

    if df_active_intervals.is_empty():
        log.warning("No active intervals found; returning no activity.")
        return pl.DataFrame()

    # --- FIX: Correct interval join logic ---
    # This correctly finds all overlaps between an activity and an active interval.
    # An overlap exists if: (activity.start < active.end) AND (activity.end > active.start)
    df_activities = df_merged.join(
        df_active_intervals, how="cross"
    ).filter(
        (pl.col("start_time") < pl.col("end")) & (pl.col("end_time") > pl.col("start"))
    ).with_columns(
        # Trim the activity to the part that falls within the active interval
        pl.max_horizontal("start_time", "start").alias("new_start"),
        pl.min_horizontal("end_time", "end").alias("new_end")
    ).select(
        pl.col("new_start").alias("start_time"),
        pl.col("new_end").alias("end_time"),
        "app", "title", "url"
    ).unique() # Remove duplicates that could arise if an activity spans multiple active periods

    if df_activities.is_empty():
        return df_activities

    return df_activities.filter(
        (pl.col("end_time") - pl.col("start_time")).dt.total_seconds() > settings.AW_MIN_DURATION_S
    )


def _prepare_final_dataframe(df_activities: pl.DataFrame, df_afk: pl.DataFrame, settings: Settings) -> pl.DataFrame:
    """Harmonizes schemas, combines activity and AFK data, and adds metadata."""
    if not df_afk.is_empty():
        df_afk = df_afk.with_columns(pl.lit(None, dtype=pl.Utf8).alias("url"))

    df_final = pl.concat([df_activities, df_afk]).sort("start_time").drop_nulls("start_time")

    if df_final.is_empty():
        return df_final

    return df_final.with_columns(
        pl.struct(["start_time", "app", "title", "url"])
          .map_elements(_generate_payload_hash, return_dtype=pl.Utf8)
          .alias("payload_hash"),
        pl.lit("digital_activity").alias("event_type"),
        pl.lit("activitywatch").alias("source"),
        pl.lit(settings.AW_HOSTNAME).alias("hostname")
    )



# ==============================================================================
# 3. DATABASE & MAIN ORCHESTRATOR FUNCTIONS
# ==============================================================================

def _write_to_duckdb(con: duckdb.DuckDBPyConnection, df_to_insert: pl.DataFrame):
    """
    Atomically upserts event data into DuckDB using two queries within a
    single transaction managed by the caller.
    """
    if df_to_insert.is_empty():
        log.info("No final events to ingest into the database.")
        return

    con.register('df_to_insert', df_to_insert)

    try:
        # Step 1: Upsert into the parent 'events' table. This handles new events
        # and ignores existing ones based on the unique payload_hash.
        log.debug("Upserting into 'events' table...")
        con.execute("""
            INSERT INTO events (id, source, event_type, start_time, end_time, payload_hash, processing_status)
            SELECT gen_random_uuid(), source, event_type::event_kind, start_time, end_time, payload_hash, 'pending'::processing_status_enum
            FROM df_to_insert
            ON CONFLICT (payload_hash) DO NOTHING;
        """)

        # Step 2: Upsert into the child 'digital_activity_data' table.
        # This join works for both newly inserted and pre-existing events because
        # Step 1 guarantees they are all in the 'events' table now.
        log.debug("Upserting into 'digital_activity_data' table...")
        con.execute("""
            INSERT INTO digital_activity_data (event_id, hostname, app, title, url)
            SELECT e.id, i.hostname, i.app, i.title, i.url
            FROM df_to_insert AS i
            JOIN events AS e ON i.payload_hash = e.payload_hash
            ON CONFLICT (event_id) DO NOTHING;
        """)

        log.info(f"Successfully upserted {df_to_insert.height} events.")

    except Exception as e:
        log.error(f"Error upserting events: {e}", exc_info=True)
        raise  # Let the caller handle the transaction rollback
    finally:
        # Always clean up the registered view
        con.unregister('df_to_insert')


def ingest_activitywatch_data(con: duckdb.DuckDBPyConnection, settings: Settings, start_utc: datetime, end_utc: datetime):
    """Main orchestrator for ingesting ActivityWatch data for a given time window."""
    log.info(f"Starting ActivityWatch ingestion for window: {start_utc} -> {end_utc}")
    client = ActivityWatchClient("lifelog-ingestor")

    async def main():
        try:
            df_window_raw, df_afk_raw, df_web_raw = await _fetch_data_async(client, settings, start_utc, end_utc)

            if df_window_raw.is_empty() and df_afk_raw.is_empty():
                log.info("No window or AFK events found in the time range. Nothing to do.")
                return

            df_afk_final, df_active_intervals = _process_afk_events(df_afk_raw, start_utc, end_utc)
            df_activities_final = _process_activity_events(
                df_window_raw, df_web_raw, df_active_intervals, settings
            )
            df_to_ingest = _prepare_final_dataframe(df_activities_final, df_afk_final, settings)
            
            # Only attempt database operations if we have data
            if not df_to_ingest.is_empty():
                _write_to_duckdb(con, df_to_ingest)
                log.info(f"Successfully ingested ActivityWatch data for window: {start_utc} -> {end_utc}")
            else:
                log.info("No events to ingest after processing.")
                
        except Exception as e:
            log.error(f"Failed to ingest ActivityWatch data: {e}", exc_info=True)
            raise  # Let the caller handle the transaction rollback

    asyncio.run(main())


def ingest_aw_window(con: duckdb.DuckDBPyConnection, settings: Settings, start_utc: datetime, end_utc: datetime):
    """
    Ingests ActivityWatch data for the specified time window.
    
    This function maintains the clean separation of concerns by only handling
    raw data ingestion. All enrichment and timeline processing is deferred 
    to the batch processor task.
    """
    log.info(f"Ingesting ActivityWatch data from {start_utc} to {end_utc}")
    ingest_activitywatch_data(con, settings, start_utc, end_utc)

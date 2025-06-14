from __future__ import annotations

"""LifeLog – ActivityWatch ingestion layer (v5.6 - AFK Consolidation & Full Integration)"""

import argparse
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence, Literal

import polars as pl
from aw_client import ActivityWatchClient

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------
def _flatten(events: list[dict]) -> pl.DataFrame:
    """Simpler JSON-based flattening used in unit tests."""
    rows = []
    for e in events:
        data = e.get("data", {})
        rows.append({
            "timestamp": e.get("timestamp"),
            "duration": e.get("duration"),
            "app": data.get("app"),
            "title": data.get("title"),
            "url": data.get("url"),
        })
    return pl.from_dicts(rows)
from aw_core.models import Event as AWEvent
from zoneinfo import ZoneInfo

from LifeLog.config import Settings # Make sure this import works and Settings is configured

# ────────────────────────────────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────────────────────────────────
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# ────────────────────────────────────────────────────────────────────────────
# Schema Definitions
# ────────────────────────────────────────────────────────────────────────────
RAW_DTYPES: dict[str, pl.DataType] = {
    "timestamp": pl.Int64,
    "duration_ms": pl.Int64,
    "app": pl.Utf8,
    "title": pl.Utf8,
    "url": pl.Utf8,
    "browser": pl.Utf8,
}
RAW_COLUMNS = list(RAW_DTYPES.keys())

OUTPUT_DTYPE: dict[str, pl.DataType] = {
    "start": pl.Datetime("ms", time_zone="UTC"),
    "end":   pl.Datetime("ms", time_zone="UTC"),
    "app":            pl.Utf8,
    "title":          pl.Utf8,
    "url":            pl.Utf8,
    "browser":        pl.Utf8,
}
OUTPUT_COLUMNS = list(OUTPUT_DTYPE.keys())

EMPTY_RAW_DF = pl.DataFrame(schema={k: v for k, v in RAW_DTYPES.items() if k in RAW_COLUMNS})
EMPTY_OUT_DF = pl.DataFrame(schema={k: v for k, v in OUTPUT_DTYPE.items() if k in OUTPUT_COLUMNS})

# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────
def _get_local_tz(settings: Settings) -> ZoneInfo:
    try:
        return ZoneInfo(settings.local_tz)
    except Exception:
        log.warning(f"Failed to load timezone '{settings.local_tz}'. Defaulting to UTC.")
        return ZoneInfo("UTC")

def _iso_bounds(day: date, *, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

def _get_hostname(client: ActivityWatchClient, settings: Settings) -> str:
    if settings.hostname_override:
        return settings.hostname_override
    try:
        info = client.get_info()
        return info["hostname"]
    except Exception as e:
        log.error(f"Failed to get hostname from AW client: {e}. Please set hostname_override or ensure client can connect.", exc_info=True)
        raise

def _flatten_events_to_df(
    events: Sequence[AWEvent],
    settings: Settings,
    source_bucket_id: str | None = None,
    bucket_type: Literal["window", "web", "afk", "unknown"] = "unknown"
) -> pl.DataFrame:
    if not events:
        return EMPTY_RAW_DF.clone()

    records = []
    for e in events:
        record = {
            "timestamp_dt": e.timestamp,
            "duration_td": e.duration,
            "data_dict": e.data if isinstance(e.data, dict) else {},
        }
        records.append(record)
    
    if not records:
        return EMPTY_RAW_DF.clone()

    df = pl.from_dicts(records)

    select_exprs = [
        pl.col("timestamp_dt").dt.epoch(time_unit="ms").alias("timestamp"),
        pl.col("duration_td").dt.total_milliseconds().alias("duration_ms"),
    ]

    actual_data_dict_fields = set()
    if "data_dict" in df.columns and isinstance(df.schema["data_dict"], pl.Struct):
        struct_dtype = df.schema["data_dict"]
        if hasattr(struct_dtype, 'fields') and isinstance(struct_dtype.fields, list):
            actual_data_dict_fields = {f.name for f in struct_dtype.fields}
    
    for raw_col_name in RAW_COLUMNS:
        if raw_col_name in ["timestamp", "duration_ms"]:
            continue

        expected_dtype = RAW_DTYPES[raw_col_name]

        if bucket_type == "afk":
            if raw_col_name == "app":
                app_name_for_afk = "SystemActivity"
                if hasattr(settings, 'afk_app_name_override') and settings.afk_app_name_override:
                    app_name_for_afk = settings.afk_app_name_override
                select_exprs.append(pl.lit(app_name_for_afk, dtype=pl.Utf8).alias("app"))
            elif raw_col_name == "title" and "status" in actual_data_dict_fields:
                select_exprs.append(pl.col("data_dict").struct.field("status").cast(expected_dtype).alias("title"))
            elif raw_col_name in ["url", "browser"]:
                select_exprs.append(pl.lit(None, dtype=expected_dtype).alias(raw_col_name))
            else: 
                select_exprs.append(pl.lit(None, dtype=expected_dtype).alias(raw_col_name))
        else: 
            potential_data_fields = {"app", "title", "url", "browser"}
            if raw_col_name in potential_data_fields and raw_col_name in actual_data_dict_fields:
                select_exprs.append(
                    pl.col("data_dict").struct.field(raw_col_name)
                    .fill_null(pl.lit(None, dtype=expected_dtype))
                    .cast(expected_dtype)
                    .alias(raw_col_name)
                )
            elif raw_col_name in potential_data_fields:
                select_exprs.append(pl.lit(None, dtype=expected_dtype).alias(raw_col_name))

    df_processed = df.select(select_exprs)
    
    final_select_expressions = []
    for col_name in RAW_COLUMNS:
        expected_dtype = RAW_DTYPES[col_name]
        if col_name in df_processed.columns:
            current_dtype = df_processed.schema[col_name]
            if current_dtype != expected_dtype:
                # Handle potential Utf8 from lit(None) needing cast to specific numeric for sum etc later if any.
                # For now, direct cast.
                final_select_expressions.append(pl.col(col_name).cast(expected_dtype).alias(col_name))
            else:
                final_select_expressions.append(pl.col(col_name))
        else:
            log.debug(f"Col '{col_name}' missing for {source_bucket_id} ({bucket_type}). Adding as null.")
            final_select_expressions.append(pl.lit(None, dtype=expected_dtype).alias(col_name))
            
    return df_processed.select(final_select_expressions)

async def _fetch_events_from_bucket(
    loop: asyncio.AbstractEventLoop,
    executor: ThreadPoolExecutor,
    client: ActivityWatchClient,
    bucket_id: str,
    start_utc: datetime,
    end_utc: datetime,
    settings: Settings,
    bucket_type: Literal["window", "web", "afk", "unknown"] = "unknown"
) -> pl.DataFrame:
    log.debug(f"Fetching {bucket_id} ({bucket_type}) from {start_utc} to {end_utc}")
    def _get_sync():
        try:
            return client.get_events(bucket_id=bucket_id, start=start_utc, end=end_utc, limit=-1)
        except Exception as e:
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json()
                    log.warning(f"Bucket {bucket_id} fetch failed ({e.response.status_code}): {e}. Server error: {error_content}")
                except Exception:
                    log.warning(f"Bucket {bucket_id} fetch failed ({e.response.status_code}): {e}.")
            else:
                log.warning(f"Bucket {bucket_id} fetch failed: {e}")
            return []
    events = await loop.run_in_executor(executor, _get_sync)
    return _flatten_events_to_df(events, settings=settings, source_bucket_id=bucket_id, bucket_type=bucket_type)

def _consolidate_afk_states(df_afk_raw_processed: pl.DataFrame) -> pl.DataFrame:
    if df_afk_raw_processed.is_empty():
        return EMPTY_RAW_DF.clone()

    df_sorted = df_afk_raw_processed.sort("timestamp")
    
    # Identify groups of consecutive identical states ('title' column holds 'afk' or 'not-afk')
    df_with_group_id = df_sorted.with_columns(
        pl.col("title").rle_id().alias("state_group_id")
    )
    
    df_consolidated = (
        df_with_group_id.group_by(["app", "title", "state_group_id"], maintain_order=True)
        .agg(
            pl.col("timestamp").first().alias("timestamp_group_start"),
            pl.col("timestamp").last().alias("last_event_timestamp_in_group"), # Timestamp of the last event in the group
            pl.col("duration_ms").last().alias("last_event_duration_in_group") # Duration of that last event
        )
        .with_columns(
            # The start of the consolidated period is the start of the first event in the group
            pl.col("timestamp_group_start").alias("timestamp"),
            # The end of the consolidated period is the end of the last event in the group
            (pl.col("last_event_timestamp_in_group") + pl.col("last_event_duration_in_group") - pl.col("timestamp_group_start"))
            .alias("duration_ms")
        )
        .select(["app", "title", "timestamp", "duration_ms"]) # Base columns for RAW_DF
        .sort("timestamp")
    )
    
    # Ensure final RAW_COLUMNS schema (url, browser will be null for SystemActivity)
    select_exprs = [
        pl.col(c).cast(RAW_DTYPES[c]) if c in df_consolidated.columns 
        else pl.lit(None, RAW_DTYPES[c]).alias(c) 
        for c in RAW_COLUMNS
    ]
    return df_consolidated.select(select_exprs)

def intersect_activity_with_active_periods(
    activity_events_df: pl.DataFrame,
    not_afk_intervals_df: pl.DataFrame, 
    settings: Settings 
) -> pl.DataFrame:
    if activity_events_df.is_empty() or not_afk_intervals_df.is_empty():
        log.debug("No activity events or no 'not-afk' periods to intersect with.")
        return EMPTY_RAW_DF.clone()

    activities_raw = activity_events_df.to_dicts()
    active_periods_input = not_afk_intervals_df.select(["timestamp", "duration_ms"]).to_dicts()
    
    active_periods = sorted(
        [{"start": p["timestamp"], "end": p["timestamp"] + p["duration_ms"]}
         for p in active_periods_input if p["duration_ms"] > 0], # Ensure valid duration for active periods
        key=lambda p: p["start"]
    )

    if not active_periods:
        log.debug("No valid 'not-afk' periods after processing. No activity will be kept after intersection.")
        return EMPTY_RAW_DF.clone()

    result_events_dicts = []
    activities_raw.sort(key=lambda x: x["timestamp"]) # Good practice

    for act_event_dict in activities_raw:
        # Skip intersection if activity itself has 0 or negative duration from previous processing
        if act_event_dict["duration_ms"] <= 0:
            continue

        act_start = act_event_dict["timestamp"]
        act_end = act_start + act_event_dict["duration_ms"]

        for active_period in active_periods:
            active_start, active_end = active_period["start"], active_period["end"]

            # Optimization: if active_period is entirely before current activity, skip
            if active_end <= act_start:
                continue
            # Optimization: if active_period is entirely after current activity, break inner loop (assuming sorted active_periods)
            if active_start >= act_end:
                break 

            overlap_start = max(act_start, active_start)
            overlap_end = min(act_end, active_end)
            overlap_duration = overlap_end - overlap_start

            if overlap_duration > 0:
                # Copy all data fields from original activity event
                new_event_data = {key: act_event_dict[key] for key in RAW_COLUMNS if key not in ["timestamp", "duration_ms"]}
                
                intersected_event = {
                    "timestamp": overlap_start,
                    "duration_ms": overlap_duration,
                    **new_event_data
                }
                result_events_dicts.append(intersected_event)
    
    if not result_events_dicts:
        log.debug("No overlapping active events found after intersection.")
        return EMPTY_RAW_DF.clone()

    df_intersected = pl.from_dicts(result_events_dicts)
    
    final_selects = [pl.col(c).cast(RAW_DTYPES[c]) if c in df_intersected.columns else pl.lit(None, RAW_DTYPES[c]).alias(c) for c in RAW_COLUMNS]
    return df_intersected.select(final_selects)


async def fetch_day_data(day: date, client: ActivityWatchClient, settings: Settings) -> pl.DataFrame:
    local_tz = _get_local_tz(settings)
    start_utc, end_utc = _iso_bounds(day, tz=local_tz)
    hostname = _get_hostname(client, settings)
    
    loop = asyncio.get_running_loop()
    max_workers = min(10, 2 + len(settings.web_bucket_map)) # Reasonable cap
    executor = ThreadPoolExecutor(max_workers=max_workers)

    # --- Fetch All Data Concurrently ---
    window_task = _fetch_events_from_bucket(loop, executor, client, settings.window_bucket_pattern.format(hostname=hostname), start_utc, end_utc, settings, bucket_type="window")
    afk_task = _fetch_events_from_bucket(loop, executor, client, settings.afk_bucket_pattern.format(hostname=hostname), start_utc, end_utc, settings, bucket_type="afk")
    
    web_fetch_tasks_map: dict[str, asyncio.Task] = {
        app_name: _fetch_events_from_bucket(loop, executor, client, bucket_pattern.format(hostname=hostname), start_utc, end_utc, settings, bucket_type="web")
        for app_name, bucket_pattern in settings.web_bucket_map.items()
    }
    
    df_window = await window_task
    df_afk_raw_processed = await afk_task # This is already flattened with app="SystemActivity"

    web_dfs_results: dict[str, pl.DataFrame] = {app_name: await task for app_name, task in web_fetch_tasks_map.items()}
    
    all_web_events_list = [
        df.with_columns(pl.lit(app_name).alias("browser_app_source")) 
        for app_name, df in web_dfs_results.items() if not df.is_empty()
    ]
    
    df_web_all = EMPTY_RAW_DF.clone().with_columns(pl.lit(None,dtype=pl.Utf8).alias("browser_app_source")) # Ensure browser_app_source exists for schema
    if all_web_events_list:
        # Ensure all DFs in list have the browser_app_source column before concat
        standardized_web_dfs = []
        for df in all_web_events_list:
            current_cols = df.columns
            select_exprs = [pl.col(c) for c in current_cols]
            if "browser_app_source" not in current_cols: # Should always be there from above
                select_exprs.append(pl.lit(None, dtype=pl.Utf8).alias("browser_app_source"))
            standardized_web_dfs.append(df.select(select_exprs))
        
        if standardized_web_dfs:
            df_web_all = pl.concat(standardized_web_dfs, how="diagonal_relaxed")


    log.info(f"Fetched {df_window.height} window, {df_web_all.height if not df_web_all.is_empty() else 0} web, {df_afk_raw_processed.height} raw AFK for {day}")

    # --- Consolidate AFK States ---
    df_afk_consolidated = _consolidate_afk_states(df_afk_raw_processed)
    log.debug(f"Consolidated {df_afk_raw_processed.height} raw AFK to {df_afk_consolidated.height} state periods.")
    
    # --- Initial Duration Filtering (Window and Web only) ---
    if (min_s := settings.min_duration_s) is not None and min_s > 0:
        min_ms = min_s * 1_000
        if not df_window.is_empty(): df_window = df_window.filter(pl.col("duration_ms") >= min_ms)
        if not df_web_all.is_empty(): df_web_all = df_web_all.filter(pl.col("duration_ms") >= min_ms)
    
    # --- Window + Web Merge ---
    processed_non_system_events_list = []
    if not df_window.is_empty():
        # Non-browser window events
        filter_expr_non_browser = ~pl.col("app").is_in(settings.browser_app_names) if settings.browser_app_names else pl.lit(True)
        df_non_browser_segment = df_window.filter(filter_expr_non_browser).select(RAW_COLUMNS)
        if not df_non_browser_segment.is_empty():
            processed_non_system_events_list.append(df_non_browser_segment)

        # Browser window events (merge with web data)
        if settings.browser_app_names:
            for browser_app_name in settings.browser_app_names:
                df_specific_browser_window = df_window.filter(pl.col("app") == browser_app_name)
                if df_specific_browser_window.is_empty():
                    continue

                # Fallback if no web data or merge fails for this browser
                browser_window_as_fallback = df_specific_browser_window.with_columns(
                    pl.col("app").alias("browser") # Tag app as browser
                ).select(RAW_COLUMNS) # url will be null

                df_specific_web = df_web_all.filter(pl.col("browser_app_source") == browser_app_name)
                
                if df_specific_web.is_empty():
                    if not browser_window_as_fallback.is_empty():
                        processed_non_system_events_list.append(browser_window_as_fallback)
                    continue
                
                df_specific_browser_window_sorted = df_specific_browser_window.sort("timestamp")
                df_specific_web_for_join = (
                    df_specific_web.select(["timestamp", "url", "title", "duration_ms"])
                    .rename({"title": "web_tab_title", "timestamp": "web_timestamp", 
                             "duration_ms": "web_duration_ms", "url": "web_url"})
                    .sort("web_timestamp")
                )

                if df_specific_web_for_join.is_empty(): # Redundant check if df_specific_web was empty
                    if not browser_window_as_fallback.is_empty():
                        processed_non_system_events_list.append(browser_window_as_fallback)
                    continue

                current_tab_info = df_specific_browser_window_sorted.join_asof(
                    df_specific_web_for_join, left_on="timestamp", right_on="web_timestamp",
                    strategy="backward", tolerance=int((settings.merge_tolerance_s or 5) * 1000)
                )
                
                successfully_merged_df = EMPTY_RAW_DF.clone() # Initialize empty
                if not current_tab_info.is_empty() and "web_timestamp" in current_tab_info.columns:
                    # Filter for actual overlap
                    current_tab_info_filtered = current_tab_info.filter(
                        pl.col("web_timestamp").is_not_null() &
                        (pl.col("web_timestamp") < (pl.col("timestamp") + pl.col("duration_ms"))) & 
                        ((pl.col("web_timestamp") + pl.col("web_duration_ms")) > pl.col("timestamp"))
                    )
                    if not current_tab_info_filtered.is_empty():
                        title_prio_web = settings.web_title_priority == "web"
                        # Coalesce URL and Title
                        final_url_expr = pl.when(pl.col("web_url").is_not_null()).then(pl.col("web_url")).otherwise(pl.col("url")).alias("url")
                        final_title_expr = pl.when(pl.col("web_url").is_not_null() & pl.col("web_tab_title").is_not_null() & title_prio_web)\
                                           .then(pl.col("web_tab_title")).otherwise(pl.col("title")).alias("title")
                        
                        successfully_merged_df = current_tab_info_filtered.with_columns(
                            final_title_expr, final_url_expr, pl.col("app").alias("browser")
                        ).select(RAW_COLUMNS)
                
                if not successfully_merged_df.is_empty():
                    processed_non_system_events_list.append(successfully_merged_df)
                elif not browser_window_as_fallback.is_empty(): # If merge failed, use the fallback
                     processed_non_system_events_list.append(browser_window_as_fallback)
    
    df_merged_non_system_activity = EMPTY_RAW_DF.clone()
    if processed_non_system_events_list:
        # Standardize DFs before concat just in case, ensuring all RAW_COLUMNS are present
        standardized_dfs = []
        for df_part in processed_non_system_events_list:
            if not df_part.is_empty():
                select_exprs_std = [pl.col(c).cast(RAW_DTYPES[c]) if c in df_part.columns else pl.lit(None, RAW_DTYPES[c]).alias(c) for c in RAW_COLUMNS]
                standardized_dfs.append(df_part.select(select_exprs_std))
        if standardized_dfs:
            df_merged_non_system_activity = pl.concat(standardized_dfs, how="vertical_relaxed")
    # --- End Window + Web Merge ---

    # --- AFK Intersection ---
    df_truly_active_events = EMPTY_RAW_DF.clone()
    df_not_afk_intervals_for_intersect = EMPTY_RAW_DF.clone()

    if not df_afk_consolidated.is_empty():
        df_not_afk_intervals_for_intersect = df_afk_consolidated.filter(pl.col("title") == "not-afk").select(["timestamp", "duration_ms"])

    if not df_merged_non_system_activity.is_empty() and not df_not_afk_intervals_for_intersect.is_empty():
        log.debug(f"Intersecting {df_merged_non_system_activity.height} non-system events with {df_not_afk_intervals_for_intersect.height} 'not-afk' periods.")
        df_truly_active_events = intersect_activity_with_active_periods(
            df_merged_non_system_activity, df_not_afk_intervals_for_intersect, settings
        )
        log.debug(f"After intersection, {df_truly_active_events.height} 'truly active' events remain.")
    elif not df_merged_non_system_activity.is_empty():
        log.warning("No 'not-afk' periods for intersection or AFK data empty. Keeping all merged non-system activity.")
        df_truly_active_events = df_merged_non_system_activity.clone() # Keep all if no AFK info
    
    # Optional: Post-AFK intersection duration filter
    if hasattr(settings, 'min_duration_s_post_afk') and (min_s_post := settings.min_duration_s_post_afk) is not None and min_s_post > 0:
        if not df_truly_active_events.is_empty():
            log.debug(f"Applying min_duration_s_post_afk ({min_s_post}s) post-AFK intersection.")
            df_truly_active_events = df_truly_active_events.filter(pl.col("duration_ms") >= (min_s_post * 1000))

    # --- Combine truly active events with CONSOLIDATED AFK events for context ---
    final_dfs_to_concat_with_afk_context = []
    if not df_truly_active_events.is_empty():
        final_dfs_to_concat_with_afk_context.append(df_truly_active_events)
    if not df_afk_consolidated.is_empty():
        final_dfs_to_concat_with_afk_context.append(df_afk_consolidated.select(RAW_COLUMNS)) # Already in RAW_COLUMNS schema from _consolidate

    df_final_activity = EMPTY_RAW_DF.clone()
    if final_dfs_to_concat_with_afk_context:
        standardized_final_dfs = [
            df.select([pl.col(c).cast(RAW_DTYPES[c]) if c in df.columns else pl.lit(None, RAW_DTYPES[c]).alias(c) for c in RAW_COLUMNS])
            for df in final_dfs_to_concat_with_afk_context if not df.is_empty()
        ]
        if standardized_final_dfs:
            df_final_activity = pl.concat(standardized_final_dfs, how="vertical_relaxed").sort("timestamp") # Sort once after all merges


    if df_final_activity.is_empty():
        log.info("%s → no rows after all processing", day)
        return EMPTY_OUT_DF.clone()

    df_output = df_final_activity.with_columns([
        pl.col("timestamp").cast(pl.Datetime("ms", time_zone="UTC")).alias("start"),
        (pl.col("timestamp") + pl.col("duration_ms")).cast(pl.Datetime("ms", time_zone="UTC")).alias("end"),
    ]) # Already sorted by timestamp, then by start

    result = df_output.select(OUTPUT_COLUMNS) # Final schema selection
    log.info("🔍 Processed data for %s. Final rows: %d (includes SystemActivity AFK/not-AFK events)", day, result.height)
    return result

def ingest(day: date | None = None, *, out_path: Path | None = None) -> Path | None:
    settings = Settings()
    target_day = day or (date.today() - timedelta(days=1))
    aw_client = ActivityWatchClient(client_name="LifeLogIngest_v5.6") # Version bump
    df_processed_day = EMPTY_OUT_DF.clone()
    try:
        df_processed_day = asyncio.run(fetch_day_data(target_day, aw_client, settings))
    except Exception as e:
        log.error(f"Failed to fetch or process data for day {target_day}: {e}", exc_info=True)

    if df_processed_day.is_empty():
        log.warning("%s resulted in empty data or processing failed; skipping write.", target_day)
        return None

    final_out_path = out_path or (settings.raw_dir / f"{target_day}.parquet")
    final_out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df_processed_day.write_parquet(final_out_path)
        log.info("✅ Wrote %d rows to %s", df_processed_day.height, final_out_path)
        return final_out_path
    except Exception as e:
        log.error(f"Failed to write Parquet file to {final_out_path}: {e}", exc_info=True)
        return None

if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-25s | %(message)s",
        level=logging.INFO,
    )
    parser = argparse.ArgumentParser(description="Ingest ActivityWatch data for LifeLog.")
    parser.add_argument("--day",type=lambda s: date.fromisoformat(s) if s else None,default=None,help="Day to ingest in YYYY-MM-DD format. Defaults to yesterday.")
    parser.add_argument("--out-path",type=Path,help="Optional custom output path for the Parquet file.")
    parser.add_argument("--debug",action="store_true",help="Enable debug logging.")
    args = parser.parse_args()

    if args.debug:
        log.setLevel(logging.DEBUG)
        # Optional: Set root logger and handlers to DEBUG to see library logs
        # root_logger = logging.getLogger()
        # root_logger.setLevel(logging.DEBUG)
        # for handler in root_logger.handlers:
        #     handler.setLevel(logging.DEBUG)
        log.debug("Debug logging enabled for LifeLog.ingestion.activitywatch.")

    ingest_result_path = ingest(args.day, out_path=args.out_path)
    if ingest_result_path:
        log.info(f"Ingestion successful: {ingest_result_path}")
    else:
        processed_day = args.day or (date.today() - timedelta(days=1))
        log.error(f"Ingestion failed or produced no data for day: {processed_day}")
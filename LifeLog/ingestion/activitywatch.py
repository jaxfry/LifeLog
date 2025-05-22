from __future__ import annotations

"""LifeLog – ActivityWatch ingestion layer (v5.3 - URL coalescing fix)"""

import argparse
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence, Literal

import polars as pl
from aw_client import ActivityWatchClient
from aw_core.models import Event as AWEvent
from zoneinfo import ZoneInfo

from LifeLog.config import Settings

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
    source_bucket_id: str | None = None
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

    potential_data_fields = {"app", "title", "url", "browser"}
    select_exprs = [
        pl.col("timestamp_dt").dt.epoch(time_unit="ms").alias("timestamp"),
        pl.col("duration_td").dt.total_milliseconds().alias("duration_ms"),
    ]

    actual_data_dict_fields = set()
    if "data_dict" in df.columns and isinstance(df.schema["data_dict"], pl.Struct):
        struct_dtype = df.schema["data_dict"]
        if hasattr(struct_dtype, 'fields') and isinstance(struct_dtype.fields, list):
            actual_data_dict_fields = {f.name for f in struct_dtype.fields}
        else:
            log.debug(f"data_dict for {source_bucket_id} is struct but couldn't list fields via .fields.")
    
    for raw_col_name in RAW_COLUMNS:
        if raw_col_name in ["timestamp", "duration_ms"]:
            continue

        expected_dtype = RAW_DTYPES[raw_col_name]
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
            if df_processed.schema[col_name] != expected_dtype:
                final_select_expressions.append(pl.col(col_name).cast(expected_dtype).alias(col_name))
            else:
                final_select_expressions.append(pl.col(col_name))
        else:
            log.debug(f"Col '{col_name}' missing before final select for {source_bucket_id}. Adding as null.")
            final_select_expressions.append(pl.lit(None, dtype=expected_dtype).alias(col_name))
            
    return df_processed.select(final_select_expressions)

async def _fetch_events_from_bucket(
    loop: asyncio.AbstractEventLoop,
    executor: ThreadPoolExecutor,
    client: ActivityWatchClient,
    bucket_id: str,
    start_utc: datetime,
    end_utc: datetime,
) -> pl.DataFrame:
    log.debug(f"Fetching {bucket_id} from {start_utc} to {end_utc}")
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
    return _flatten_events_to_df(events, source_bucket_id=bucket_id)

async def fetch_day_data(day: date, client: ActivityWatchClient, settings: Settings) -> pl.DataFrame:
    local_tz = _get_local_tz(settings)
    start_utc, end_utc = _iso_bounds(day, tz=local_tz)
    hostname = _get_hostname(client, settings)
    
    loop = asyncio.get_running_loop()
    max_workers = min(10, 2 + len(settings.web_bucket_map))
    executor = ThreadPoolExecutor(max_workers=max_workers)

    core_tasks = []
    window_bucket_id = settings.window_bucket_pattern.format(hostname=hostname)
    core_tasks.append(_fetch_events_from_bucket(loop, executor, client, window_bucket_id, start_utc, end_utc))
    afk_bucket_id = settings.afk_bucket_pattern.format(hostname=hostname)
    core_tasks.append(_fetch_events_from_bucket(loop, executor, client, afk_bucket_id, start_utc, end_utc))
    
    web_fetch_tasks, web_app_names_for_tasks = [], []
    for app_name, bucket_pattern in settings.web_bucket_map.items():
        web_bucket_id = bucket_pattern.format(hostname=hostname)
        web_fetch_tasks.append(
            _fetch_events_from_bucket(loop, executor, client, web_bucket_id, start_utc, end_utc)
        )
        web_app_names_for_tasks.append(app_name)
    
    all_task_results = await asyncio.gather(*core_tasks, *web_fetch_tasks)
    
    df_window, df_afk = all_task_results[0], all_task_results[1]
    raw_web_dfs_results = all_task_results[len(core_tasks):]
    
    all_web_events_list = []
    for i, app_name_key in enumerate(web_app_names_for_tasks):
        df_single_web = raw_web_dfs_results[i]
        if not df_single_web.is_empty():
            all_web_events_list.append(
                df_single_web.with_columns(pl.lit(app_name_key).alias("browser_app_source"))
            )
    
    df_web_all = EMPTY_RAW_DF.clone().with_columns(pl.lit(None,dtype=pl.Utf8).alias("browser_app_source"))
    if all_web_events_list:
        df_web_all = pl.concat(all_web_events_list, how="diagonal_relaxed")

    log.info(f"Fetched {df_window.height} window, {df_web_all.height if not df_web_all.is_empty() else 0} web, {df_afk.height} AFK events for {day}")

    if (min_s := settings.min_duration_s) is not None and min_s > 0:
        min_ms = min_s * 1_000
        if not df_window.is_empty(): df_window = df_window.filter(pl.col("duration_ms") >= min_ms)
        if not df_web_all.is_empty(): df_web_all = df_web_all.filter(pl.col("duration_ms") >= min_ms)
    
    df_non_browser_window = EMPTY_RAW_DF.clone()
    if not df_window.is_empty():
        filter_expr = ~pl.col("app").is_in(settings.browser_app_names) if settings.browser_app_names else pl.lit(True)
        df_non_browser_window = df_window.filter(filter_expr).select(RAW_COLUMNS)

    merged_browser_dfs_list = []
    if not df_window.is_empty() and settings.browser_app_names: # Ensure there are browser apps to process
        for browser_app_name in settings.browser_app_names:
            df_specific_browser_window = df_window.filter(pl.col("app") == browser_app_name)
            if df_specific_browser_window.is_empty():
                continue

            # Default case: no web data for this specific browser, or web data is empty
            # Prepare the browser window data with 'browser' tag and null 'url'
            browser_window_as_merged = df_specific_browser_window.with_columns(
                pl.col("app").alias("browser") # app is the browser
            ).select(RAW_COLUMNS) # url will be null by default from RAW_COLUMNS

            df_specific_web = df_web_all.filter(pl.col("browser_app_source") == browser_app_name)
            
            if df_specific_web.is_empty():
                if not browser_window_as_merged.is_empty():
                    merged_browser_dfs_list.append(browser_window_as_merged)
                continue # No web data to merge for this browser
            
            df_specific_browser_window_sorted = df_specific_browser_window.sort("timestamp")
            
            df_specific_web_for_join = (
                df_specific_web
                .select(["timestamp", "url", "title", "duration_ms"])
                .rename({
                    "title": "web_tab_title", 
                    "timestamp": "web_timestamp", 
                    "duration_ms": "web_duration_ms",
                    "url": "web_url"  # RENAMED for coalescing
                })
                .sort("web_timestamp")
            )

            if df_specific_web_for_join.is_empty(): # Should be caught above, but safe check
                if not browser_window_as_merged.is_empty():
                    merged_browser_dfs_list.append(browser_window_as_merged)
                continue

            current_tab_info = df_specific_browser_window_sorted.join_asof(
                df_specific_web_for_join,
                left_on="timestamp",
                right_on="web_timestamp",
                strategy="backward", # Default strategy, consider "forward" or "nearest" if issues persist
                tolerance=int((settings.merge_tolerance_s or 5) * 1000)
            )
            
            if not current_tab_info.is_empty() and "web_timestamp" in current_tab_info.columns:
                current_tab_info = current_tab_info.filter(
                    pl.col("web_timestamp").is_not_null() &
                    (pl.col("web_timestamp") < (pl.col("timestamp") + pl.col("duration_ms"))) & 
                    ((pl.col("web_timestamp") + pl.col("web_duration_ms")) > pl.col("timestamp"))
                )
            
            if not current_tab_info.is_empty():
                title_priority_is_web = settings.web_title_priority == "web"
                
                final_url_expr = (
                    pl.when(pl.col("web_url").is_not_null())
                    .then(pl.col("web_url"))
                    .otherwise(pl.col("url")) # original 'url' from window event (usually null)
                    .alias("url")
                )

                final_title_expr = (
                    pl.when(pl.col("web_url").is_not_null() & pl.col("web_tab_title").is_not_null() & title_priority_is_web)
                    .then(pl.col("web_tab_title"))
                    .otherwise(pl.col("title")) 
                    .alias("title")
                )
                merged_df = current_tab_info.with_columns(
                    final_title_expr,
                    final_url_expr, # APPLY COALESCED URL
                    pl.col("app").alias("browser")
                ).select(RAW_COLUMNS)
                merged_browser_dfs_list.append(merged_df)
            elif not browser_window_as_merged.is_empty(): # If join resulted in empty but window events existed
                 merged_browser_dfs_list.append(browser_window_as_merged)


    all_dfs_to_concat = []
    if not df_non_browser_window.is_empty():
        all_dfs_to_concat.append(df_non_browser_window)
    
    processed_browser_events_exist = False
    if merged_browser_dfs_list:
        for df_item in merged_browser_dfs_list:
            if not df_item.is_empty():
                all_dfs_to_concat.append(df_item)
                processed_browser_events_exist = True
    
    # If no browser apps were defined in settings, or no browser events were processed/merged,
    # but there were window events for apps that *could* have been browsers, add them.
    if not processed_browser_events_exist and not df_window.is_empty() and settings.browser_app_names:
        df_unmerged_browsers = df_window.filter(pl.col("app").is_in(settings.browser_app_names))
        if not df_unmerged_browsers.is_empty():
            all_dfs_to_concat.append(
                df_unmerged_browsers.with_columns(
                    pl.col("app").alias("browser") # Tag as browser
                ).select(RAW_COLUMNS) # URL will be null
            )

    df_merged_activity = EMPTY_RAW_DF.clone()
    if all_dfs_to_concat:
        standardized_dfs = []
        for temp_df in all_dfs_to_concat:
            if not temp_df.is_empty():
                select_cols_for_concat = []
                for r_col in RAW_COLUMNS:
                    if r_col in temp_df.columns:
                        select_cols_for_concat.append(pl.col(r_col).cast(RAW_DTYPES[r_col]))
                    else:
                        select_cols_for_concat.append(pl.lit(None, dtype=RAW_DTYPES[r_col]).alias(r_col))
                standardized_dfs.append(temp_df.select(select_cols_for_concat))
        if standardized_dfs:
            df_merged_activity = pl.concat(standardized_dfs, how="vertical_relaxed")

    if df_merged_activity.is_empty():
        log.info("%s → no rows after merging and filtering", day)
        return EMPTY_OUT_DF.clone()

    df_final_activity = df_merged_activity
    
    if df_final_activity.is_empty():
        log.info("%s → no rows before final output conversion", day)
        return EMPTY_OUT_DF.clone()

    df_output = df_final_activity.with_columns([
        pl.col("timestamp").cast(pl.Datetime("ms", time_zone="UTC")).alias("start"),
        (pl.col("timestamp") + pl.col("duration_ms"))
          .cast(pl.Datetime("ms", time_zone="UTC")).alias("end"),
    ])

    result = df_output.select(OUTPUT_COLUMNS).sort("start")
    log.info("🔍 Processed data for %s. Final rows: %d", day, result.height)
    return result

def ingest(day: date | None = None, *, out_path: Path | None = None) -> Path | None:
    settings = Settings()
    target_day = day or (date.today() - timedelta(days=1))
    aw_client = ActivityWatchClient(client_name="LifeLogIngest_v5.3")
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
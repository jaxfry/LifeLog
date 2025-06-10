from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import json
import polars as pl
from zoneinfo import ZoneInfo

from LifeLog.config import Settings
from LifeLog.models import TimelineEntry

router = APIRouter()

@router.get("/api/day/{day_str}")
def get_day_data(day_str: str): # 'day_str' is the selected LOCAL day string
    settings = Settings()

    try:
        day = date.fromisoformat(day_str)  # Manually parse the date string
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date format for '{day_str}'. Please use YYYY-MM-DD.")

    # Determine UTC range for the selected local day
    try:
        target_tz = ZoneInfo(settings.local_tz)
    except Exception as e:
        print(f"Warning: Invalid local_tz '{settings.local_tz}' in settings. Falling back to UTC. Error: {e}") # Consider proper logging
        target_tz = timezone.utc

    local_dt_start = datetime.combine(day, time.min, tzinfo=target_tz)
    local_dt_end = datetime.combine(day, time.max, tzinfo=target_tz) # Inclusive end of the local day

    utc_dt_start = local_dt_start.astimezone(timezone.utc)
    utc_dt_end = local_dt_end.astimezone(timezone.utc) # This is the UTC timestamp of the last moment of the local day

    # Determine Parquet files to read (data is stored by UTC date)
    # An event belongs to a local day if any part of it falls within that local day.
    # The Parquet files are named by the UTC date they contain.
    utc_date_for_start_of_local_day = utc_dt_start.date()
    utc_date_for_end_of_local_day = utc_dt_end.date()

    files_to_read = set()
    files_to_read.add(settings.curated_dir / f"{utc_date_for_start_of_local_day}.parquet")
    if utc_date_for_start_of_local_day != utc_date_for_end_of_local_day: # If local day spans two UTC days
        files_to_read.add(settings.curated_dir / f"{utc_date_for_end_of_local_day}.parquet")

    all_dfs = []
    for timeline_path_candidate in files_to_read:
        if timeline_path_candidate.exists():
            try:
                df_single_utc_day = pl.read_parquet(timeline_path_candidate)
                if not df_single_utc_day.is_empty(): # Ensure DataFrame is not empty before processing
                    all_dfs.append(df_single_utc_day)
            except Exception as e:
                print(f"Error reading or processing parquet file {timeline_path_candidate}: {e}") # Replace with proper logging

    entries: list[dict] = []
    if all_dfs:
        # Concatenate DataFrames if multiple files were read
        df_combined = pl.concat(all_dfs) if len(all_dfs) > 1 else all_dfs[0]
        
        # Deduplicate if events were in multiple files (e.g. if files had overlaps, though unlikely by date naming)
        # Assuming 'start' and 'activity' or another combination can uniquely identify an event if needed for deduplication.
        # For now, assuming Parquet files per UTC day are distinct and concatenation is sufficient.
        # df_combined = df_combined.unique(subset=['start', 'activity'], keep='first') # Example deduplication

        # Filter for entries that overlap with the local day's UTC window
        # Overlap condition: (EntryStart < LocalDayEndUTC) AND (EntryEnd > LocalDayStartUTC)
        # Timestamps in Parquet are assumed to be UTC.
        df_filtered = df_combined.filter(
            (pl.col("start") < utc_dt_end) & (pl.col("end") > utc_dt_start)
        )
        
        # Sort by start time before converting to dicts
        if not df_filtered.is_empty():
            df_sorted = df_filtered.sort("start")
            for row in df_sorted.to_dicts():
                entry = TimelineEntry(**row)
                entries.append(json.loads(entry.model_dump_json()))
    
    # Load the daily summary. The summary file is named after the local day.
    summary_path = settings.summary_dir / f"{day}.json" # Use the parsed 'day' object
    summary_data = {}
    if summary_path.exists():
        try:
            summary_data = json.loads(summary_path.read_text())
        except Exception as e:
            print(f"Error reading summary file {summary_path}: {e}") # Replace with proper logging

    return JSONResponse(content={
        "summary": summary_data,
        "entries": entries,
    })

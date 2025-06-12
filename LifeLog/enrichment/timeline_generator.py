from __future__ import annotations
from datetime import date, datetime, timedelta, timezone, time # Added time
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
import logging # Added logging
import polars as pl # Added polars
import os # Added os
import sys # Added sys
from pydantic import BaseModel, Field, field_validator, model_validator, RootModel
from google import genai # Main SDK import
from google.genai import types as genai_types # For type hints like GenerationConfig
from google.auth.exceptions import DefaultCredentialsError # For auth errors
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError # Python 3.9+
import duckdb
from LifeLog.database import get_connection

# Ensure LifeLog can be imported when run as a script
# This assumes the script is located at /Users/jaxon/Coding/LifeLog/LifeLog/enrichment/timeline_generator.py
# The project root /Users/jaxon/Coding/LifeLog needs to be in sys.path for `from LifeLog.config import Settings` to work.
_project_root = Path(__file__).resolve().parents[2] # Go up two levels from LifeLog/enrichment/ to LifeLog/
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


from LifeLog.config import Settings
from LifeLog.prompts import TIMELINE_ENRICHMENT_SYSTEM_PROMPT # Added import
from LifeLog.enrichment.project_classifier import ProjectResolver

log = logging.getLogger(__name__)

# ── Monkey-patch HTTPX (Optional) ────────────
try:
    import httpx._models as _httpx_models

    def _normalize_header_value_lifelog(value: Union[str, bytes], encoding: str | None):
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        try:
            return value.encode(encoding or "ascii")
        except UnicodeEncodeError:
            return value.encode("utf-8", errors="surrogateescape")

    if hasattr(_httpx_models, '_normalize_header_value') and \
       _httpx_models._normalize_header_value.__code__.co_varnames[:2] == ('value', 'encoding'):
        _httpx_models._normalize_header_value = _normalize_header_value_lifelog
    else:
        log.debug("Skipping httpx monkey-patch due to signature mismatch or missing attribute.")
except ImportError:
    log.debug("httpx not found, skipping monkey-patch.")
except Exception as e:
    log.warning(f"Failed to apply httpx monkey-patch: {e}")

# --- Pydantic Models ---
class EnrichedTimelineEntry(BaseModel):
    event_id: Optional[str] = Field(default=None, description="Unique event ID for DB row.")
    start: datetime = Field(description="Start time UTC ISO format.")
    end: datetime = Field(description="End time UTC ISO format.")
    activity: str = Field(description="Short verb phrase.")
    project: Optional[str] = Field(default=None, description="Project/course name.")
    notes: Optional[str] = Field(default=None, description="1-2 sentence summary.")

    @field_validator('start', 'end', mode='before')
    @classmethod
    def parse_datetime_utc(cls, v):
        if isinstance(v, str):
            dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        if isinstance(v, datetime):
            return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)
        raise ValueError("Invalid datetime format")

    @model_validator(mode='after')
    def check_start_before_end(cls, values):
        if values.start and values.end and values.start > values.end : # Strict greater than
             raise ValueError(f"End time ({values.end}) must be after or same as start time ({values.start}).")
        if values.start == values.end and values.start is not None: # Allow zero duration
            pass
        elif values.start and values.end and values.start >= values.end:
             raise ValueError(f"End time ({values.end}) must be after start time ({values.start}).")
        return values

class TimelineResponse(RootModel[List[EnrichedTimelineEntry]]):
    root: List[EnrichedTimelineEntry]
    def __iter__(self):
        return iter(self.root)
    def __getitem__(self, item):
        return self.root[item]
    def __len__(self):
        return len(self.root)


# Helper to get local timezone
def _get_local_tz(settings: Settings) -> ZoneInfo:
    try:
        return ZoneInfo(settings.local_tz)
    except ZoneInfoNotFoundError:
        log.warning(f"Timezone '{settings.local_tz}' not found in system database. Defaulting to UTC.")
        return timezone.utc
    except Exception as e: # Catch other potential errors like invalid string format
        log.error(f"Error initializing ZoneInfo with '{settings.local_tz}': {e}. Defaulting to UTC.")
        return timezone.utc

def _load_raw_data_for_local_day(local_day: date, settings: Settings) -> pl.DataFrame:
    target_tz = _get_local_tz(settings)

    local_dt_start = datetime.combine(local_day, time.min, tzinfo=target_tz)
    local_dt_end = datetime.combine(local_day, time.max, tzinfo=target_tz)

    utc_dt_start = local_dt_start.astimezone(timezone.utc)
    utc_dt_end = local_dt_end.astimezone(timezone.utc)

    utc_date_for_start = utc_dt_start.date()
    utc_date_for_end = utc_dt_end.date()

    files_to_read_paths = set()
    files_to_read_paths.add(settings.raw_dir / f"{utc_date_for_start}.parquet")
    if utc_date_for_start != utc_date_for_end:
        files_to_read_paths.add(settings.raw_dir / f"{utc_date_for_end}.parquet")

    all_dfs = []
    # Define expected raw schema for empty DataFrame case and for ensuring consistency
    raw_file_schema = {
        "start": pl.Datetime("ms", time_zone="UTC"), "end": pl.Datetime("ms", time_zone="UTC"),
        "app": pl.Utf8, "title": pl.Utf8, "url": pl.Utf8, "browser": pl.Utf8,
    }

    for raw_file_path in sorted(list(files_to_read_paths)): # Sort for deterministic order
        if raw_file_path.exists():
            try:
                df_single_utc_day = pl.read_parquet(raw_file_path)
                if not df_single_utc_day.is_empty():
                    # Ensure DataFrame conforms to the expected schema, selecting only necessary columns
                    # and casting if necessary. This helps prevent issues with unexpected columns/dtypes.
                    # For now, we assume read_parquet handles dtypes well if source is consistent.
                    # A more robust version might explicitly select and cast columns.
                    all_dfs.append(df_single_utc_day.select(list(raw_file_schema.keys())))
            except Exception as e:
                log.error(f"Error reading or processing raw parquet file {raw_file_path}: {e}")
        else:
            log.warning(f"Raw data file not found: {raw_file_path}")

    if not all_dfs:
        log.warning(f"No raw data found for local day {local_day} (UTC range: {utc_dt_start} to {utc_dt_end})")
        return pl.DataFrame(schema=raw_file_schema)

    df_combined = pl.concat(all_dfs, how="diagonal_relaxed") # Use diagonal_relaxed for schema evolution if necessary
    
    # Deduplicate events that might span across UTC day file boundaries if read twice
    # or if source data had exact duplicates. Based on 'start' as primary key for an event.
    df_combined = df_combined.unique(subset=["start", "app", "title"], keep="first", maintain_order=True)

    # Filter events to be strictly within the local day's UTC range
    # Ensure 'start' and 'end' columns are present and are of datetime type
    if "start" not in df_combined.columns or "end" not in df_combined.columns or \
       not isinstance(df_combined["start"].dtype, pl.Datetime) or \
       not isinstance(df_combined["end"].dtype, pl.Datetime):
        log.error(f"Combined raw DataFrame missing or has incorrect type for 'start' or 'end' columns for {local_day}. Schema: {df_combined.schema}")
        return pl.DataFrame(schema=raw_file_schema)

    # Ensure datetimes are timezone-aware (UTC) for comparison
    # Polars datetimes read from parquet with tz info should already be aware
    df_filtered_for_local_day = df_combined.filter(
        (pl.col("start") < utc_dt_end) & (pl.col("end") > utc_dt_start)
    )

    log.info(f"Loaded {df_filtered_for_local_day.height} raw events from {len(files_to_read_paths)} file(s) for local day {local_day} (spanning UTC {utc_dt_start} to {utc_dt_end}).")
    return df_filtered_for_local_day

def _load_unenriched_events_for_day(local_day: date, settings: Settings) -> List[Dict[str, Any]]:
    """Load events from DuckDB that need enrichment (category IS NULL and before today).
    Falls back to file-based loading if database is unavailable and fallback is enabled."""
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT event_id, start_time, end_time, app_name, window_title
                FROM timeline_events
                WHERE category IS NULL AND date = ? AND start_time < CURRENT_DATE
                ORDER BY start_time ASC
                """,
                (str(local_day),)
            )
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        log.error(f"Failed to load unenriched events from database for {local_day}: {e}")
        if settings.enable_database_fallback:
            log.info("Attempting to load from file-based system...")
            return _load_unenriched_events_from_files(local_day, settings)
        else:
            raise

def _load_unenriched_events_from_files(local_day: date, settings: Settings) -> List[Dict[str, Any]]:
    """Fallback method to load events from parquet files when database is unavailable."""
    log.warning(f"Using file-based fallback for {local_day}")
    
    # Load raw data and convert to expected format
    df_raw = _load_raw_data_for_local_day(local_day, settings)
    if df_raw.is_empty():
        return []
    
    events = []
    for i, row in enumerate(df_raw.iter_rows(named=True)):
        events.append({
            "event_id": f"file_fallback_{local_day}_{i}",  # Generate temporary ID
            "start_time": row["start"],
            "end_time": row["end"],
            "app_name": row["app"],
            "window_title": row["title"]
        })
    
    return events

def _load_and_prepare_input_df(local_day: date, settings: Settings) -> pl.DataFrame:
    df_raw_for_local_day = _load_raw_data_for_local_day(local_day, settings)

    prompt_schema = {
        "time_utc": pl.Utf8, "duration_s": pl.Int32, "app": pl.Utf8,
        "title": pl.Utf8, "url": pl.Utf8
    }

    if df_raw_for_local_day.is_empty():
        log.warning(f"No raw events for local day {local_day} after loading and initial filtering stage.")
        return pl.DataFrame(schema=prompt_schema)

    # Ensure 'start' and 'end' columns exist before trying to use them
    if "start" not in df_raw_for_local_day.columns or "end" not in df_raw_for_local_day.columns:
        log.error(f"Raw data for {local_day} is missing 'start' or 'end' columns after loading. Columns: {df_raw_for_local_day.columns}")
        return pl.DataFrame(schema=prompt_schema)

    df_activities = df_raw_for_local_day.filter(pl.col("app") != settings.afk_app_name_override)
    if df_activities.is_empty():
        log.info(f"No non-AFK activities for local day {local_day}.")
        return pl.DataFrame(schema=prompt_schema)

    # Ensure 'start' and 'end' columns are present before calculating duration
    if "start" not in df_activities.columns or "end" not in df_activities.columns:
        log.error(f"df_activities for {local_day} is missing 'start' or 'end' columns before duration calculation. Columns: {df_activities.columns}")
        return pl.DataFrame(schema=prompt_schema) # Return empty with expected schema

    df_activities = df_activities.with_columns(
        ((pl.col("end") - pl.col("start")).dt.total_seconds()).alias("duration_s")
    )

    if settings.enrichment_min_duration_s > 0:
        df_activities = df_activities.filter(pl.col("duration_s") >= settings.enrichment_min_duration_s)

    if df_activities.is_empty():
        log.info(f"No activities after duration filter for local day {local_day}.")
        return pl.DataFrame(schema=prompt_schema)

    truncate_limit = settings.enrichment_prompt_truncate_limit
    ellipsis_suffix = "…"

    # Sort by the original 'start' datetime column before selecting and formatting for the prompt
    df_activities_sorted = df_activities.sort("start")

    df_for_prompt = df_activities_sorted.select(
        pl.col("start").dt.strftime("%H:%M:%S").alias("time_utc"),
        pl.col("duration_s").round(0).cast(pl.Int32),
        pl.col("app"),
        pl.when(pl.col("title").fill_null("").str.len_chars() > truncate_limit)
          .then(pl.col("title").fill_null("").str.slice(0, truncate_limit) + pl.lit(ellipsis_suffix))
          .otherwise(pl.col("title").fill_null(""))
          .alias("title"),
        pl.when(pl.col("url").fill_null("").str.len_chars() > truncate_limit)
          .then(pl.col("url").fill_null("").str.slice(0, truncate_limit) + pl.lit(ellipsis_suffix))
          .otherwise(pl.col("url").fill_null(""))
          .alias("url"),
    )
    # No sort needed here as df_activities_sorted was already sorted by the true start time.

    log.info(f"Prepared {df_for_prompt.height} activity events for LLM prompt for local day {local_day}.")
    return df_for_prompt

def _build_llm_prompt(day: date, events_df: pl.DataFrame, settings: Settings) -> str:
    if events_df.is_empty():
        return ""

    max_events_for_prompt = settings.enrichment_max_events
    events_table_md = (
        events_df.head(max_events_for_prompt)
        .to_pandas()
        .to_markdown(index=False)
    )

    schema_description = (
        '[{"start": "YYYY-MM-DDTHH:MM:SSZ",'
        '"end": "YYYY-MM-DDTHH:MM:SSZ",'
        '"activity": "string",'
        '"project": "string | null",'
        '"notes": "string | null"}]'
    )

    prompt_text = TIMELINE_ENRICHMENT_SYSTEM_PROMPT.format(
        day_iso=day.isoformat(),
        schema_description=schema_description,
        events_table_md=events_table_md
    )
    return prompt_text


def _invoke_llm_and_parse(day: date, prompt_text: str, settings: Settings) -> List[EnrichedTimelineEntry]:
    if not prompt_text:
        log.warning(f"Empty prompt for {day}, skipping LLM call.")
        return []
    # Always call LLM; DB-centric pipeline, skip file cache
    raw_json_response_str: Optional[str] = None
    try:
        client: Optional[genai.Client] = None
        if not os.getenv("GEMINI_API_KEY"):
            log.error("GEMINI_API_KEY environment variable not set. This is required for the google-genai SDK with Gemini Developer API.")
            raise ValueError("GEMINI_API_KEY not set.")
        api_key_from_env = os.getenv("GEMINI_API_KEY")
        client = genai.Client(api_key=api_key_from_env)
        generation_config_obj = genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=settings.enrichment_llm_temperature,
        )
        retries = settings.enrichment_llm_retries
        response_obj = None
        for attempt in range(retries):
            try:
                log.debug(f"Attempt {attempt+1}/{retries} to call Gemini.")
                response_obj = client.models.generate_content(
                    model=settings.model_name,
                    contents=prompt_text,
                    config=generation_config_obj
                )
                raw_json_response_str = response_obj.text
                if response_obj.prompt_feedback and response_obj.prompt_feedback.block_reason:
                    log.error(f"Prompt for {day} was blocked by Gemini. Reason: {response_obj.prompt_feedback.block_reason}")
                    return []
                break
            except Exception as e:
                log.warning(f"Gemini API error on attempt {attempt+1}/{retries} for {day}: {type(e).__name__} - {e}")
                if response_obj and response_obj.prompt_feedback and response_obj.prompt_feedback.block_reason:
                    log.error(f"Prompt for {day} was blocked during retry by Gemini (associated with exception). Reason: {response_obj.prompt_feedback.block_reason}")
                    return []
                if attempt + 1 == retries:
                    log.error(f"Max retries reached for Gemini API for {day}.")
                    raise
                time.sleep((2 ** attempt) * settings.enrichment_llm_retry_delay_base_s)
    except Exception as e:
        log.error(f"Failed to initialize Gemini client or call LLM: {e}")
        raise
    if not raw_json_response_str:
        log.warning(f"No response from LLM for {day} (API failure or blocked).")
        return []
    try:
        timeline_response = TimelineResponse.model_validate_json(raw_json_response_str)
        enriched_entries = timeline_response.root
        log.info(f"Successfully parsed {len(enriched_entries)} entries from LLM response for {day}.")
        return enriched_entries
    except Exception as e:
        log.error(f"Failed to parse/validate LLM JSON response for {day}: {e}")
        log.error(f"Problematic JSON string snippet: {raw_json_response_str[:500]}...")
        raise
def _post_process_entries(day: date, entries: List[EnrichedTimelineEntry], settings: Settings) -> List[EnrichedTimelineEntry]:
    if not entries: return []
    entries.sort(key=lambda e: e.start)
    project_resolver = ProjectResolver(settings)
    for entry in entries:
        entry.project = project_resolver.resolve(entry.project, entry.activity, entry.notes, entry.start)
    if not settings.enrichment_enable_post_merge: return entries
    merged_entries: List[EnrichedTimelineEntry] = []
    for current_entry in entries:
        if not merged_entries: merged_entries.append(current_entry); continue
        last = merged_entries[-1]
        gap_s = (current_entry.start - last.end).total_seconds()
        act_match = last.activity.lower() == current_entry.activity.lower()
        proj_match = (last.project or "").lower() == (current_entry.project or "").lower()
        if act_match and proj_match and 0 <= gap_s <= settings.enrichment_merge_gap_s:
            last.end = max(last.end, current_entry.end)
            if current_entry.notes and current_entry.notes not in (last.notes or ""):
                last.notes = (last.notes or "") + f" | {current_entry.notes}"
        else: merged_entries.append(current_entry)
    log.info(f"Post-processing for {day}: {len(entries)} initial -> {len(merged_entries)} merged entries.")
    return merged_entries


def _ensure_day_boundaries(
    day: date,
    entries: List[EnrichedTimelineEntry],
    settings: Settings,
) -> List[EnrichedTimelineEntry]:
    """Ensure timeline covers the full local day by filling leading/trailing gaps."""
    tz = _get_local_tz(settings)
    day_start_utc = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
    day_end_utc = (datetime.combine(day, time.min, tzinfo=tz) + timedelta(days=1)).astimezone(timezone.utc)

    if not entries:
        return [
            EnrichedTimelineEntry(
                start=day_start_utc,
                end=day_end_utc,
                activity="Idle / Away",
                project=None,
                notes="Device was idle or user was away all day.",
            )
        ]

    entries.sort(key=lambda e: e.start)
    first = entries[0]
    if first.start > day_start_utc:
        entries.insert(
            0,
            EnrichedTimelineEntry(
                start=day_start_utc,
                end=first.start,
                activity="Idle / Away",
                project=None,
                notes="Device was idle or user was away at start of day.",
            ),
        )

    last = entries[-1]
    if last.end < day_end_utc:
        entries.append(
            EnrichedTimelineEntry(
                start=last.end,
                end=day_end_utc,
                activity="Idle / Away",
                project=None,
                notes="Device was idle or user was away until the end of the day.",
            )
        )

    return entries

def run_enrichment_for_day(day: date, settings: Settings) -> None:
    log.info(f"Starting enrichment process for day: {day.isoformat()}")
    try:
        if settings.use_database:
            _run_database_enrichment(day, settings)
        else:
            _run_file_based_enrichment(day, settings)
    except Exception as e:
        log.error(f"Enrichment failed for day {day}: {e}", exc_info=True)
        if settings.enable_backwards_compatibility and settings.use_database:
            log.info("Attempting fallback to file-based enrichment...")
            try:
                _run_file_based_enrichment(day, settings)
                log.info(f"✅ Fallback enrichment completed for {day}")
            except Exception as fallback_error:
                log.error(f"❌ Fallback enrichment also failed for {day}: {fallback_error}")
                raise
        else:
            raise

def _run_database_enrichment(day: date, settings: Settings) -> None:
    """Run database-based enrichment pipeline."""
    unenriched_events = _load_unenriched_events_for_day(day, settings)
    if not unenriched_events:
        log.info(f"No unenriched events found for {day} in DB.")
        return
    
    log.info(f"Loaded {len(unenriched_events)} unenriched events from DB for {day}.")
    
    # Prepare DataFrame for LLM prompt (simulate previous logic, but from DB rows)
    import pandas as pd
    df_for_prompt = pd.DataFrame([
        {
            "time_utc": e["start_time"].strftime("%H:%M:%S"),
            "duration_s": int((e["end_time"] - e["start_time"]).total_seconds()),
            "app": e["app_name"],
            "title": e["window_title"] or "",
            "url": ""
        }
        for e in unenriched_events
        if (e["end_time"] - e["start_time"]).total_seconds() >= settings.enrichment_min_duration_s
    ])
    
    if df_for_prompt.empty:
        log.warning(f"No suitable events for LLM for {day}. Skipping.")
        return
    
    # Build prompt and call LLM
    prompt_text = _build_llm_prompt(day, pl.from_pandas(df_for_prompt), settings)
    enriched_llm_entries = _invoke_llm_and_parse(day, prompt_text, settings)
    
    # Map event_ids back to enriched entries (assume 1:1 order for now)
    for entry, raw in zip(enriched_llm_entries, unenriched_events):
        entry.event_id = raw["event_id"]
    
    final_entries = _post_process_entries(day, enriched_llm_entries, settings)
    
    # Update DB
    _update_enriched_events_in_db(final_entries, settings)
    log.info(f"✅ Enriched and updated {len(final_entries)} events for {day} in DB.")

def _run_file_based_enrichment(day: date, settings: Settings) -> None:
    """Run file-based enrichment pipeline as fallback."""
    log.info(f"Running file-based enrichment for {day}")
    
    df_for_prompt = _load_and_prepare_input_df(day, settings)
    if df_for_prompt.is_empty():
        log.warning(f"No suitable events for LLM for {day}. Skipping.")
        return
    
    prompt_text = _build_llm_prompt(day, df_for_prompt, settings)
    enriched_llm_entries = _invoke_llm_and_parse(day, prompt_text, settings)
    final_entries = _post_process_entries(day, enriched_llm_entries, settings)
    final_entries = _ensure_day_boundaries(day, final_entries, settings)
    
    # Save to file for backwards compatibility
    _save_enriched_timeline_to_file(day, final_entries, settings)
    log.info(f"✅ File-based enrichment completed for {day}")

def _save_enriched_timeline_to_file(day: date, entries: List[EnrichedTimelineEntry], settings: Settings) -> None:
    """Save enriched timeline to file for backwards compatibility."""
    output_path = settings.curated_dir / f"{day.isoformat()}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    timeline_data = [entry.model_dump(mode='json') for entry in entries]
    import json
    with open(output_path, 'w') as f:
        json.dump(timeline_data, f, indent=2, default=str)
    
    log.info(f"Saved {len(entries)} enriched entries to {output_path}")

def _update_enriched_events_in_db(enriched_entries: List[EnrichedTimelineEntry], settings: Settings):
    """Batch update timeline_events with enrichment results using a transaction. 
    Logs progress and implements sophisticated retry logic for partial batch failures."""
    if not enriched_entries:
        return

    batch_size = getattr(settings, 'enrichment_batch_size', 50)
    max_retries = getattr(settings, 'enrichment_max_retries', 3)
    
    def process_batch_with_recovery(batch: List[EnrichedTimelineEntry], attempt: int = 1):
        """Process a batch of entries with sophisticated retry and recovery logic."""
        try:
            with get_connection() as conn:
                conn.execute("BEGIN TRANSACTION;")
                success_count = 0
                failed_entries = []
                
                for idx, entry in enumerate(batch):
                    if not entry.event_id:
                        log.warning(f"Skipping entry without event_id: {entry.activity}")
                        continue
                    
                    try:
                        # Check if record exists first
                        cur = conn.cursor()
                        cur.execute("SELECT COUNT(*) FROM timeline_events WHERE event_id = ?", (entry.event_id,))
                        if cur.fetchone()[0] == 0:
                            log.warning(f"Event ID {entry.event_id} not found in database, skipping")
                            continue
                            
                        conn.execute(
                            """
                            UPDATE timeline_events
                            SET category = ?, notes = ?, project = ?, last_modified = CURRENT_TIMESTAMP
                            WHERE event_id = ?
                            """,
                            (
                                entry.activity,  # category
                                entry.notes,
                                entry.project,
                                entry.event_id,
                            )
                        )
                        success_count += 1
                        
                        # Log progress for large batches
                        if len(batch) > 20 and (idx + 1) % 10 == 0:
                            log.debug(f"Processed {idx + 1}/{len(batch)} entries in current batch")
                            
                    except Exception as e:
                        log.error(f"Failed to update individual entry {entry.event_id}: {e}")
                        failed_entries.append(entry)
                
                conn.commit()
                log.info(f"Batch {attempt}: Successfully updated {success_count}/{len(batch)} entries")
                
                # Handle partial failures with individual retry strategy
                if failed_entries:
                    if attempt < max_retries:
                        log.info(f"Retrying {len(failed_entries)} failed entries individually (attempt {attempt + 1})")
                        # Try each failed entry individually to isolate specific issues
                        individual_successes = 0
                        permanent_failures = []
                        
                        for failed_entry in failed_entries:
                            try:
                                with get_connection() as retry_conn:
                                    retry_conn.execute("BEGIN TRANSACTION;")
                                    retry_conn.execute(
                                        """
                                        UPDATE timeline_events
                                        SET category = ?, notes = ?, project = ?, last_modified = CURRENT_TIMESTAMP
                                        WHERE event_id = ?
                                        """,
                                        (failed_entry.activity, failed_entry.notes, failed_entry.project, failed_entry.event_id)
                                    )
                                    retry_conn.commit()
                                    individual_successes += 1
                            except Exception as retry_error:
                                log.error(f"Individual retry failed for {failed_entry.event_id}: {retry_error}")
                                permanent_failures.append(failed_entry)
                        
                        log.info(f"Individual retry recovered {individual_successes}/{len(failed_entries)} entries")
                        
                        if permanent_failures and attempt < max_retries:
                            # Final attempt for permanent failures
                            log.info(f"Final attempt for {len(permanent_failures)} persistent failures")
                            process_batch_with_recovery(permanent_failures, max_retries)
                        elif permanent_failures:
                            log.error(f"Permanently failed to update {len(permanent_failures)} entries: {[e.event_id for e in permanent_failures]}")
                    else:
                        log.error(f"Permanently failed to update {len(failed_entries)} entries after {max_retries} attempts")
                        
        except Exception as e:
            try:
                conn.rollback()
                log.info("Transaction rolled back due to error")
            except:
                pass  # Ignore rollback errors if no transaction is active
            
            log.error(f"Batch {attempt} failed completely: {e}")
            
            # Retry the entire batch if we haven't exceeded max retries
            if attempt < max_retries:
                import time
                backoff_delay = min(2 ** attempt, 30)  # Exponential backoff capped at 30s
                log.info(f"Retrying entire batch after {backoff_delay}s delay (attempt {attempt + 1})")
                time.sleep(backoff_delay)
                process_batch_with_recovery(batch, attempt + 1)
            else:
                log.error(f"Batch permanently failed after {max_retries} attempts")
                raise

    # Process entries in batches with progress tracking
    total_batches = (len(enriched_entries) + batch_size - 1) // batch_size
    log.info(f"Processing {len(enriched_entries)} entries in {total_batches} batches (batch size: {batch_size})")
    
    for i in range(0, len(enriched_entries), batch_size):
        batch = enriched_entries[i:i + batch_size]
        batch_num = i // batch_size + 1
        log.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} entries)...")
        process_batch_with_recovery(batch)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-7s] [%(name)-25s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    import argparse
    parser = argparse.ArgumentParser(description="Enrich LifeLog data.")
    parser.add_argument("--day", type=lambda s: date.fromisoformat(s) if s else None, default=None, help="Day YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--days-ago", type=int, default=None, help="Days ago (overrides --day)")
    parser.add_argument("--force-llm", action="store_true", help="Force LLM re-query")
    parser.add_argument("--force-processing", action="store_true", help="Force full re-processing")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args(); settings = Settings()
    if args.debug: logging.getLogger("LifeLog").setLevel(logging.DEBUG); log.setLevel(logging.DEBUG); log.debug("Debug on.")
    if args.force_llm: settings.enrichment_force_llm = True
    if args.force_processing: settings.enrichment_force_processing_all = True
    target_day = (date.today() - timedelta(days=args.days_ago)) if args.days_ago is not None else (args.day or (date.today() - timedelta(days=1)))
    log.info(f"Target day: {target_day.isoformat()}")
    if run_enrichment_for_day(target_day, settings): log.info("Enrichment done.")
    else: log.error(f"Enrichment failed for {target_day.isoformat()}.")
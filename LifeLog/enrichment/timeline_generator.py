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
    event_id: str = Field(description="UUID of the source event")
    start: datetime = Field(description="Start time UTC ISO format.")
    end: datetime = Field(description="End time UTC ISO format.")
    activity: str = Field(description="Short verb phrase or category.")
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

    cache_path = settings.enriched_cache_dir / f"{day}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    raw_json_response_str: Optional[str] = None

    if cache_path.exists() and not settings.enrichment_force_llm:
        log.info(f"Using cached LLM response for {day} from {cache_path}")
        raw_json_response_str = cache_path.read_text()
    else:
        log.info(f"Querying Gemini for {day} with model {settings.model_name}. Prompt length: ~{len(prompt_text)} chars.")
        
        client: Optional[genai.Client] = None
        try:
            if not os.getenv("GEMINI_API_KEY"):
                log.error("GEMINI_API_KEY environment variable not set. This is required for the google-genai SDK with Gemini Developer API.")
                raise ValueError("GEMINI_API_KEY not set.")
            api_key_from_env = os.getenv("GEMINI_API_KEY")
            client = genai.Client(api_key=api_key_from_env)
        except DefaultCredentialsError as e:
            log.error(f"Google Cloud Default Credentials not found: {e}. If using Vertex, ensure you are authenticated.")
            raise
        except Exception as e:
            log.error(f"Failed to initialize Gemini client: {e}")
            raise
        
        if client is None:
            log.error("Gemini client was not initialized.")
            raise RuntimeError("Gemini client initialization failed.")

        generation_config_obj = genai_types.GenerateContentConfig( # Corrected to GenerateContentConfig
            response_mime_type="application/json",
            temperature=settings.enrichment_llm_temperature,
        )
        
        retries = settings.enrichment_llm_retries
        response_obj = None # Initialize response_obj before the loop
        for attempt in range(retries):
            try:
                log.debug(f"Attempt {attempt+1}/{retries} to call Gemini.")
                response_obj = client.models.generate_content( # Assign to response_obj directly
                    model=settings.model_name,
                    contents=prompt_text,
                    config=generation_config_obj
                )
                raw_json_response_str = response_obj.text
                
                # *** CORRECTED CHECK for prompt_feedback ***
                if response_obj.prompt_feedback and response_obj.prompt_feedback.block_reason:
                    log.error(f"Prompt for {day} was blocked by Gemini. Reason: {response_obj.prompt_feedback.block_reason}")
                    return [] 
                break # Successful call, exit retry loop
            except Exception as e:
                log.warning(f"Gemini API error on attempt {attempt+1}/{retries} for {day}: {type(e).__name__} - {e}")
                
                # *** CORRECTED CHECK for prompt_feedback in except block ***
                # This check is for a less common scenario where an exception might also populate prompt_feedback.
                # response_obj here would be from the current failed attempt if it got that far.
                if response_obj and response_obj.prompt_feedback and response_obj.prompt_feedback.block_reason:
                    log.error(f"Prompt for {day} was blocked during retry by Gemini (associated with exception). Reason: {response_obj.prompt_feedback.block_reason}")
                    return [] 
                
                if attempt + 1 == retries:
                    log.error(f"Max retries reached for Gemini API for {day}.")
                    raise # Re-raise the last exception
                time.sleep( (2 ** attempt) * settings.enrichment_llm_retry_delay_base_s )

        if raw_json_response_str:
            cache_path.write_text(raw_json_response_str)
            log.info(f"Cached LLM JSON response for {day} to {cache_path}")
        # If raw_json_response_str is None here, it means all retries failed, or it was blocked (handled), or prompt was empty (handled).
        # The next check outside this `else` block will correctly handle it.


    if not raw_json_response_str:
        # This handles cases where cache was not used AND LLM call failed or returned no content (e.g. blocked, or all retries failed)
        log.warning(f"No response from LLM for {day} (either from cache or API).")
        return []

    try:
        timeline_response = TimelineResponse.model_validate_json(raw_json_response_str)
        enriched_entries = timeline_response.root
        log.info(f"Successfully parsed {len(enriched_entries)} entries from LLM response for {day}.")
        return enriched_entries
    except Exception as e:
        log.error(f"Failed to parse/validate LLM JSON response for {day}: {e}")
        log.error(f"Problematic JSON string snippet: {raw_json_response_str[:500]}...")
        error_cache_path = settings.enriched_cache_dir / f"{day}.error.txt"
        error_cache_path.write_text(raw_json_response_str)
        log.error(f"Saved erroneous LLM response to {error_cache_path}")
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

from LifeLog.database import get_connection

def run_enrichment_for_day(day: date, settings: Settings) -> int | None:
    """Enrich timeline events stored in the database for the given day."""
    log.info(f"Starting enrichment process for {day}")
    query = (
        "SELECT event_id, start_time, end_time, app_name, window_title "
        "FROM timeline_events "
        "WHERE date = ? AND category IS NULL AND date < CURRENT_DATE "
        "ORDER BY start_time"
    )
    with get_connection() as conn:
        rows = conn.execute(query, (day.isoformat(),)).fetchall()
    if not rows:
        log.info(f"No unenriched events for {day}")
        return 0
    events = []
    for r in rows:
        event_id, start, end, app, title = r
        duration_s = int((end - start).total_seconds())
        events.append({
            "event_id": str(event_id),
            "time_utc": start.strftime("%H:%M:%S"),
            "duration_s": duration_s,
            "app": app,
            "title": title or "",
        })
    header = "| event_id | time_utc | duration_s | app | title |"
    sep = "|---|---|---|---|---|"
    rows_md = [header, sep]
    for ev in events[: settings.enrichment_max_events]:
        rows_md.append(
            f"| {ev['event_id']} | {ev['time_utc']} | {ev['duration_s']} | {ev['app']} | {ev['title']} |"
        )
    events_table_md = "\n".join(rows_md)
    schema_description = '[{"event_id": "uuid", "category": "string", "project": "string | null", "notes": "string | null"}]'
    prompt_text = TIMELINE_ENRICHMENT_SYSTEM_PROMPT.format(
        day_iso=day.isoformat(),
        schema_description=schema_description,
        events_table_md=events_table_md,
    )
    enriched_entries = _invoke_llm_and_parse(day, prompt_text, settings)
    if not enriched_entries:
        log.warning(f"LLM returned no entries for {day}")
        return 0
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("BEGIN")
        try:
            for e in enriched_entries:
                cur.execute(
                    "UPDATE timeline_events SET category = ?, notes = ?, project = ?, last_modified = NOW() WHERE event_id = ?",
                    (e.activity, e.notes, e.project, e.event_id),
                )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            log.error(f"Failed to update events for {day}: {exc}")
            return None
    log.info(f"Updated {len(enriched_entries)} events for {day}")
    return len(enriched_entries)

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
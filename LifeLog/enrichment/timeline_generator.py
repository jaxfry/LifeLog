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

class ProjectResolver:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.project_aliases: Dict[str, str] = settings.project_aliases or {}

    def resolve(self, project_name: Optional[str], activity_text: str, notes_text: Optional[str]) -> Optional[str]:
        if project_name:
            norm_project_name = project_name.lower()
            for alias, canonical_name in self.project_aliases.items():
                if alias.lower() == norm_project_name:
                    return canonical_name
            return project_name # Return original if no alias found
        
        combined_text = activity_text.lower() + (notes_text.lower() if notes_text else "")
        for keyword, canonical_name in self.project_aliases.items():
             if keyword.lower() in combined_text:
                 return canonical_name
        return None

# --- Core Logic ---

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

    prompt_text = f"""You are an expert timeline curator and analyst. Your objective is to transform a raw log of computer events for the date {day.isoformat()}
into a concise, meaningful, user-centric narrative of the day.

The events are provided in a markdown table with columns: **time_utc, duration_s, app, title, url**.
- `time_utc` (HH:MM:SS, already UTC) all share the same calendar date {day.isoformat()}.
- `duration_s` is the length of that raw event in seconds.

Return **only** a JSON list of “EnrichedTimelineEntry” objects that exactly match this schema:
{schema_description}

──────────────────────────────────────────────────────────
### Output rules – MUST follow
• Produce **one** JSON array; the output must begin with `[` and end with `]` (no NDJSON, no Markdown).  
• `start` and `end` **must** be ISO-8601 strings (e.g. “2025-05-22T09:33:10Z”) — **never** Unix epoch numbers.  
• Merge consecutive *Idle / Away* blocks if the gap between them is < 5 minutes.  
• Only populate `"project"` when the block directly advances that project; social chat or generic browsing ⇒ `null`.  
──────────────────────────────────────────────────────────

#### 1 · Identify coherent activity blocks & keep them sequential
* Process raw rows strictly in order; each row can belong to only one block.  
* Short context-preserving app switches (quick look-ups, alt-tabs) stay inside the surrounding block.  
* A substantial context switch (≈ ≥ 10–15 min) on an unrelated task starts a new block.  
* Preserve distinct short events (e.g. “Sent email to X”) if they constitute a complete action.

#### 2 · Define `start` / `end`
* `start` = `time_utc` of the first row in the block.  
* `end`   = (`time_utc` + `duration_s`) of the last row in that block.  
* No overlaps: every new block must start ≥ the previous block’s end.

#### 3 · Craft a specific `activity`
Concise verb phrase (≤ 6 words) that captures the user’s primary focus.  
*Good:* “Debugging payment API bug”.  *Avoid:* “Using VS Code”.

#### 4 · Determine `project` (optional)
Name the project/course if obviously identifiable from filenames, repo paths, meeting titles, etc.; otherwise `null`.

#### 5 · Write rich `notes` (1–3 sentences)
* **Mandatory:** Pull concrete nouns from `title` and `url` (file names, PR numbers, video titles, Discord channels…).  
* Reflect narrative flow if the block contains multiple stages (research → code → test).  
* Summarise many similar items (“Reviewed 5 PRs, incl. #101, #103”).  
* Idle / AFK blocks may use “System locked”, “User away” where applicable.

#### General quality bar
* Accurate, gap-free, easy to scan, and genuinely useful to the user.

──────────────────────────────────────────────────────────
Raw Usage Events for {day.isoformat()}:
{events_table_md}

JSON Output (strictly follow the schema – single array, no comments, no trailing commas):
"""
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
        entry.project = project_resolver.resolve(entry.project, entry.activity, entry.notes)
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

def run_enrichment_for_day(day: date, settings: Settings) -> Path | None:
    log.info(f"Starting enrichment process for day: {day.isoformat()}")
    output_file_path = settings.curated_dir / f"{day}.parquet"
    output_file_path.parent.mkdir(parents=True, exist_ok=True)
    if output_file_path.exists() and not settings.enrichment_force_processing_all:
        log.info(f"Skipping {day}, output exists: {output_file_path}")
        return output_file_path
    try:
        df_for_prompt = _load_and_prepare_input_df(day, settings)
        enriched_llm_entries: List[EnrichedTimelineEntry] = []
        if df_for_prompt.is_empty():
            log.warning(f"No suitable events for LLM for {day}. Will proceed to check for trailing AFK.")
            # enriched_llm_entries remains empty
        else:
            prompt_text = _build_llm_prompt(day, df_for_prompt, settings)
            enriched_llm_entries = _invoke_llm_and_parse(day, prompt_text, settings)

        final_entries = _post_process_entries(day, enriched_llm_entries, settings) # Pass LLM entries here

        # --- BEGIN ADDITION: Capture trailing AFK period ---
        current_last_event_end_utc: Optional[datetime] = None
        if final_entries:
            current_last_event_end_utc = final_entries[-1].end
        else:
            # If LLM produced no entries, or post-processing resulted in no entries,
            # start checking for AFK from the beginning of the day.
            local_tz_for_day_start = _get_local_tz(settings)
            current_last_event_end_utc = datetime.combine(day, time.min, tzinfo=local_tz_for_day_start).astimezone(timezone.utc)

        # Determine the actual end of the local day in UTC (exclusive boundary)
        local_tz_for_day_end = _get_local_tz(settings)
        day_end_boundary_utc = (datetime.combine(day, time.min, tzinfo=local_tz_for_day_end) + timedelta(days=1)).astimezone(timezone.utc)

        if current_last_event_end_utc < day_end_boundary_utc:
            df_raw_for_day_check = _load_raw_data_for_local_day(day, settings)

            if not df_raw_for_day_check.is_empty() and 'start' in df_raw_for_day_check.columns:
                # Check for any *non-AFK* activity in the raw data in the gap
                df_non_afk_in_gap = df_raw_for_day_check.filter(
                    (pl.col("app") != settings.afk_app_name_override) &
                    (pl.col("start") >= current_last_event_end_utc) &
                    (pl.col("start") < day_end_boundary_utc)
                )

                if df_non_afk_in_gap.is_empty():
                    # No non-AFK activity in the gap. The gap is AFK or unrecorded.
                    if day_end_boundary_utc > current_last_event_end_utc: # Ensure positive duration
                        afk_block_start = current_last_event_end_utc
                        afk_block_end = day_end_boundary_utc
                        
                        log.info(f"Identified trailing Idle / Away period for {day} from {afk_block_start.isoformat()} to {afk_block_end.isoformat()}")
                        
                        new_idle_entry = EnrichedTimelineEntry(
                            start=afk_block_start,
                            end=afk_block_end,
                            activity="Idle / Away",
                            project=None,
                            notes="Device was idle or user was away until the end of the day."
                        )

                        merged_with_previous = False
                        if final_entries:
                            last_entry = final_entries[-1]
                            # Check if last entry is idle and if the new idle block starts very close to its end
                            if ("idle" in last_entry.activity.lower() or "away" in last_entry.activity.lower()) and \
                               (new_idle_entry.start - last_entry.end).total_seconds() < settings.enrichment_merge_gap_s:
                                log.info(f"Extending previous Idle / Away entry (ending {last_entry.end.isoformat()}) to {new_idle_entry.end.isoformat()}")
                                last_entry.end = new_idle_entry.end
                                # Optionally update notes if needed, e.g., if the new one is more generic
                                # last_entry.notes = new_idle_entry.notes # Or some combination
                                merged_with_previous = True
                        
                        if not merged_with_previous:
                            log.info(f"Appending new trailing Idle / Away entry for {day}.")
                            final_entries.append(new_idle_entry)
                else:
                    log.info(f"Non-AFK activity found after {current_last_event_end_utc.isoformat()} for day {day}. Not adding trailing idle block.")
            elif df_raw_for_day_check.is_empty():
                 log.info(f"Raw data for {day} was empty for trailing AFK check. Not adding trailing idle block.")
            else: # df_raw_for_day_check is not empty but 'start' column missing (should not happen with _load_raw_data_for_local_day)
                 log.warning(f"Raw data for {day} missing 'start' column for trailing AFK check. Not adding trailing idle block.")

        # --- END ADDITION ---

        if not final_entries: # Check again after potential addition
            log.warning(f"No entries after post-processing and trailing AFK check for {day}. Writing empty Parquet.")
            # Define schema for empty DataFrame based on EnrichedTimelineEntry fields
            empty_schema = {
                field_name: pl.Datetime(time_unit='us', time_zone='UTC') if annotation == datetime else pl.Utf8
                for field_name, field_info in EnrichedTimelineEntry.model_fields.items()
                for annotation in [field_info.annotation] # Get actual type
            }
            pl.DataFrame(schema=empty_schema).write_parquet(output_file_path)
            return output_file_path # Return path to empty file
        else:
            output_data = [e.model_dump(mode='json') for e in final_entries]
            # Ensure datetimes from model_dump (which are ISO strings) are converted back to Polars Datetime
            df_output = pl.from_dicts(output_data).with_columns([
                pl.col("start").str.to_datetime(time_unit='us').dt.replace_time_zone("UTC"),
                pl.col("end").str.to_datetime(time_unit='us').dt.replace_time_zone("UTC"),
                # Ensure other columns are Utf8, especially project and notes which can be None
                pl.col("activity").cast(pl.Utf8),
                pl.col("project").cast(pl.Utf8, strict=False), # Fill None with null
                pl.col("notes").cast(pl.Utf8, strict=False)    # Fill None with null
            ])
            # Select columns in desired order, matching EnrichedTimelineEntry fields
            ordered_columns = list(EnrichedTimelineEntry.model_fields.keys())
            df_output = df_output.select(ordered_columns)

            df_output.write_parquet(output_file_path)
            log.info(f"✅ Enriched {len(final_entries)} entries for {day} to {output_file_path}")
        return output_file_path
    except FileNotFoundError: # This might be too broad if _load_raw_data_for_local_day raises it for missing raw files
        log.error(f"A required file was not found during enrichment for {day}.", exc_info=True) # Log with traceback
        return None
    except Exception as e:
        log.error(f"Unhandled error during enrichment for day {day}: {e}", exc_info=True)
        return None

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
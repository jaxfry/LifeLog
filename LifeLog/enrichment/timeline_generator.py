from __future__ import annotations

import json
import logging
import os
import time 
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

import polars as pl
from pydantic import BaseModel, Field, field_validator, model_validator, RootModel
from google import genai # Main SDK import
from google.genai import types as genai_types # For type hints like GenerationConfig
from google.auth.exceptions import DefaultCredentialsError # For auth errors

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
    def __iter__(self): return iter(self.root)
    def __getitem__(self, item): return self.root[item]
    def __len__(self): return len(self.root)

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
def _load_and_prepare_input_df(day: date, settings: Settings) -> pl.DataFrame:
    ingested_file_path = settings.raw_dir / f"{day}.parquet"
    if not ingested_file_path.exists():
        log.error(f"Ingested data file not found for {day}: {ingested_file_path}")
        raise FileNotFoundError(f"Ingested data file not found for {day}")
    df_raw_ingested = pl.read_parquet(ingested_file_path)
    log.info(f"Loaded {df_raw_ingested.height} raw ingested events for {day}.")
    df_activities = df_raw_ingested.filter(pl.col("app") != settings.afk_app_name_override)
    if df_activities.is_empty(): return df_activities
    df_activities = df_activities.with_columns(((pl.col("end") - pl.col("start")).dt.total_seconds()).alias("duration_s"))
    if settings.enrichment_min_duration_s > 0:
        df_activities = df_activities.filter(pl.col("duration_s") >= settings.enrichment_min_duration_s)
    if df_activities.is_empty(): return df_activities
    truncate_limit = settings.enrichment_prompt_truncate_limit; ellipsis_suffix = "…"
    df_for_prompt = df_activities.select(
        pl.col("start").dt.strftime("%H:%M:%S").alias("time_utc"),
        pl.col("duration_s").round(0).cast(pl.Int32),
        pl.col("app"),
        pl.when(pl.col("title").fill_null("").str.len_chars() > truncate_limit).then(pl.col("title").fill_null("").str.slice(0, truncate_limit) + pl.lit(ellipsis_suffix)).otherwise(pl.col("title").fill_null("")).alias("title"),
        pl.when(pl.col("url").fill_null("").str.len_chars() > truncate_limit).then(pl.col("url").fill_null("").str.slice(0, truncate_limit) + pl.lit(ellipsis_suffix)).otherwise(pl.col("url").fill_null("")).alias("url"),
    ).sort("time_utc")
    log.info(f"Prepared {df_for_prompt.height} activity events for LLM prompt for {day}.")
    return df_for_prompt

def _build_llm_prompt(day: date, events_df: pl.DataFrame, settings: Settings) -> str:
    if events_df.is_empty(): return ""
    max_events_for_prompt = settings.enrichment_max_events
    events_table_md = events_df.head(max_events_for_prompt).to_pandas().to_markdown(index=False)
    schema_description = """[{"start": "YYYY-MM-DDTHH:MM:SSZ","end": "YYYY-MM-DDTHH:MM:SSZ","activity": "string","project": "string | null","notes": "string | null"}]"""
    prompt = f"You are a meticulous LifeLog assistant..." # Keep your detailed prompt structure
    # (Shortened here for brevity, but use your full detailed prompt from before)
    prompt = f"""
You are a meticulous LifeLog assistant. Your task is to analyze a list of raw computer activity events for the date {day.isoformat()}
and group them into meaningful, consolidated timeline entries.

The raw events are provided in a table with columns: time_utc, duration_s, app, title, url.
'time_utc' is the start time of the event in UTC. The date for all events is {day.isoformat()}.
'duration_s' is the duration of the event in seconds.

Your goal is to output a JSON list of "EnrichedTimelineEntry" objects.
Each EnrichedTimelineEntry represents a distinct, user-perceived activity or task.
The JSON output MUST be a list of objects, strictly adhering to this schema for each object:
{schema_description}

Key Instructions:
1.  Merge Logically: Combine consecutive raw events that clearly belong to the same overarching activity and project.
2.  Determine Start/End (UTC): "start" is UTC start of earliest event, "end" is UTC end of latest event in group. Format: "YYYY-MM-DDTHH:MM:SSZ".
3.  Activity Description ("activity"): Be specific and concise. e.g., "Editing 'script.py' in VS Code".
4.  Project Identification ("project"): Infer project. Null if not clear.
5.  Notes ("notes"): Summarize key details.
6.  Context is Key: Use app, title, and url.
7.  Chronological Order: Output list must be chronological.
8.  Handle Short Activities: Short, distinct activities are separate entries.
9.  Focus on User Intent.

Respond ONLY with a single, valid JSON list. Do not include any other text, explanations, or markdown formatting.

Raw Events for {day.isoformat()} (UTC times, up to {max_events_for_prompt} shown):
{events_table_md}

JSON Output:
"""
    return prompt

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
        if df_for_prompt.is_empty():
            log.warning(f"No suitable events for LLM for {day}. Writing empty Parquet.")
            empty_schema = {f.name: pl.Datetime if f.annotation==datetime else pl.Utf8 for f_name, f in EnrichedTimelineEntry.model_fields.items()}
            pl.DataFrame(schema=empty_schema).write_parquet(output_file_path); return output_file_path
        prompt_text = _build_llm_prompt(day, df_for_prompt, settings)
        enriched_llm = _invoke_llm_and_parse(day, prompt_text, settings)
        if not enriched_llm:
            log.warning(f"LLM returned no entries for {day}. Writing empty Parquet.")
            empty_schema = {f.name: pl.Datetime if f.annotation==datetime else pl.Utf8 for f_name, f in EnrichedTimelineEntry.model_fields.items()}
            pl.DataFrame(schema=empty_schema).write_parquet(output_file_path); return output_file_path
        final_entries = _post_process_entries(day, enriched_llm, settings)
        if not final_entries:
            log.warning(f"No entries after post-processing for {day}. Writing empty Parquet.")
            empty_schema = {f.name: pl.Datetime if f.annotation==datetime else pl.Utf8 for f_name, f in EnrichedTimelineEntry.model_fields.items()}
            pl.DataFrame(schema=empty_schema).write_parquet(output_file_path)
        else:
            output_data = [e.model_dump(mode='json') for e in final_entries]
            df_output = pl.from_dicts(output_data).with_columns([
                pl.col("start").str.to_datetime().dt.replace_time_zone("UTC"),
                pl.col("end").str.to_datetime().dt.replace_time_zone("UTC"),
                pl.all().exclude(["start", "end"]).cast(pl.Utf8) # Cast others to Utf8
            ])
            df_output.write_parquet(output_file_path)
            log.info(f"✅ Enriched {len(final_entries)} entries for {day} to {output_file_path}")
        return output_file_path
    except FileNotFoundError: return None
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
from __future__ import annotations

import json
import logging
import os
import time
import re 
from datetime import date, datetime, timedelta, timezone 
from pathlib import Path
from typing import List, Optional, Dict

import polars as pl
from google import genai
from google.auth.exceptions import DefaultCredentialsError 
from google.genai import types as genai_types
from pydantic import BaseModel, Field, PositiveInt, field_validator, model_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError # Import specific error

from LifeLog.config import Settings
from LifeLog.enrichment.timeline_generator import EnrichedTimelineEntry 
from LifeLog.prompts import DAILY_SUMMARY_JSON_SCHEMA, DAILY_SUMMARY_SYSTEM_PROMPT # Added import

log = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    EMBED_MODEL_NAME = "sentence-transformers/paraphrase-MiniLM-L6-v2"
    EMBED_MODEL = SentenceTransformer(EMBED_MODEL_NAME, device="cpu")
    log.info(f"Successfully loaded sentence embedding model: {EMBED_MODEL_NAME}")
except ImportError as e:
    log.warning(f"sentence_transformers not available: {e}. Summary embeddings will be disabled.")
    EMBED_MODEL = None
except Exception as e:
    log.error(f"Failed to load sentence embedding model: {EMBED_MODEL_NAME}. Error: {e}", exc_info=True)
    EMBED_MODEL = None

# --- Pydantic Schemas ---
# (Keep your Pydantic schemas as they are, they seem fine)
class Block(BaseModel):
    start_time: str = Field(description="HH:MM format representing the start of the block.")
    end_time: str = Field(description="HH:MM format representing the end of the block.")
    label: str = Field(description="Concise label for the block, often 'Project · Activity'.")
    project: Optional[str] = Field(default=None)
    activity: str
    summary: str = Field(description="1-2 sentence summary of the block's content.")
    tags: List[str] = Field(default_factory=list)
    embedding: Optional[List[float]] = Field(default=None, description="Sentence embedding of the block summary.")

    @field_validator('start_time', 'end_time', mode='before')
    @classmethod
    def validate_time_format(cls, value):
        if isinstance(value, str) and re.match(r"^\d{2}:\d{2}$", value):
            return value
        if isinstance(value, datetime):
            return value.strftime("%H:%M")
        raise ValueError("Time must be in HH:MM format string or a datetime object.")

class Stats(BaseModel):
    total_active_time_min: int 
    focus_time_min: int        
    number_blocks: int         
    top_project: Optional[str] = None
    top_activity: Optional[str] = None 

class DailySummary(BaseModel):
    date: date 
    blocks: List[Block]
    day_summary: str = Field(description="A 2-3 sentence narrative overview of the day.")
    stats: Stats
    version: int = 2 

    @field_validator('date', mode='before')
    @classmethod
    def parse_date(cls, value):
        if isinstance(value, str):
            return date.fromisoformat(value)
        if isinstance(value, date):
            return value
        raise ValueError("Invalid date format")

# --- Deterministic Pre-grouping ---
# (_group_adjacent_entries remains the same)
def _group_adjacent_entries(
    entries: list[EnrichedTimelineEntry], 
    gap_s: int = 300 
) -> list[list[EnrichedTimelineEntry]]:
    if not entries: return []
    sorted_entries = sorted(entries, key=lambda x: x.start)
    groups: list[list[EnrichedTimelineEntry]] = []; current_group: list[EnrichedTimelineEntry] = []
    for entry in sorted_entries:
        if not current_group: current_group.append(entry)
        else:
            last_entry_in_group = current_group[-1]
            project_match = (entry.project or "").lower() == (last_entry_in_group.project or "").lower()
            activity_match = entry.activity.lower() == last_entry_in_group.activity.lower()
            time_gap_acceptable = (entry.start - last_entry_in_group.end).total_seconds() <= gap_s
            if project_match and activity_match and time_gap_acceptable: current_group.append(entry)
            else: groups.append(current_group); current_group = [entry]
    if current_group: groups.append(current_group)
    log.info(f"Pre-grouped {len(entries)} timeline entries into {len(groups)} initial blocks (gap_s={gap_s}).")
    return groups


def _format_groups_for_llm_prompt(
    groups: list[list[EnrichedTimelineEntry]], 
    settings: Settings
) -> str:
    rows = []
    if not groups:
        return "No activity groups to display."

    # --- FIX for Timezone Warning Spam ---
    local_tz_obj: Optional[ZoneInfo] = None
    warned_about_tz = False # Flag to ensure warning is logged only once
    if settings.local_tz:
        try:
            local_tz_obj = ZoneInfo(settings.local_tz)
        except ZoneInfoNotFoundError: # Catch specific error
            log.warning(f"Timezone '{settings.local_tz}' not found. Using UTC for prompt times.")
            warned_about_tz = True # Mark that we've warned
        except Exception as e: # Catch other potential ZoneInfo errors
            log.warning(f"Invalid timezone '{settings.local_tz}' (Error: {e}). Using UTC for prompt times.")
            warned_about_tz = True # Mark that we've warned
    # --- END FIX for Timezone Warning Spam ---

    for group in groups:
        if not group: continue 

        first_entry = group[0]
        last_entry = group[-1]
        start_dt = first_entry.start
        end_dt = last_entry.end

        if local_tz_obj: # Use the successfully created local_tz_obj
            start_dt = start_dt.astimezone(local_tz_obj)
            end_dt = end_dt.astimezone(local_tz_obj)
        # If local_tz_obj is None (due to invalid settings.local_tz or it not being set),
        # start_dt and end_dt remain UTC, and the warning (if any) has already been logged once.

        start_time_str = start_dt.strftime("%H:%M")
        end_time_str = end_dt.strftime("%H:%M")
        project_str = first_entry.project or ""
        activity_str = first_entry.activity 
        notes_list = [e.notes for e in group if e.notes]
        notes_str = " | ".join(notes_list) if notes_list else ""
        
        rows.append([
            start_time_str, end_time_str, project_str, activity_str, 
            notes_str[:settings.summary_prompt_notes_truncate_limit]
        ])

    if not rows: return "No displayable activity groups after formatting."
    header = ["start_local_or_utc", "end_local_or_utc", "project", "activity", "condensed_notes"] # Adjusted header name
    md_table = "| " + " | ".join(header) + " |\n"
    md_table += "| " + " | ".join(["---"] * len(header)) + " |\n"
    for row in rows:
        md_table += "| " + " | ".join(str(x) for x in row) + " |\n"
    return md_table

# --- Gemini Prompt & Call ---
# (_build_summary_prompt remains the same)
def _build_summary_prompt(day_iso: str, pre_grouped_markdown: str, settings: Settings) -> str:
    json_schema_for_prompt = DAILY_SUMMARY_JSON_SCHEMA
    time_context = f"(times in table are {settings.local_tz if settings.local_tz else 'UTC'})"
    prompt = DAILY_SUMMARY_SYSTEM_PROMPT.format(
        day_iso=day_iso,
        time_context=time_context,
        json_schema_for_prompt=json_schema_for_prompt,
        pre_grouped_markdown=pre_grouped_markdown
    )
    return prompt.strip()


def _invoke_gemini_for_summary(
    client: genai.Client, 
    prompt: str, 
    settings: Settings
) -> str:
    model_name = settings.summary_model_name if settings.summary_model_name is not None else settings.model_name
    temperature = settings.summary_llm_temperature if settings.summary_llm_temperature is not None else settings.enrichment_llm_temperature
    
    _retries_val = settings.summary_llm_retries
    if not isinstance(_retries_val, int) or _retries_val < 0 :
        _retries_val = settings.enrichment_llm_retries
    if not isinstance(_retries_val, int) or _retries_val < 0:
        _retries_val = 3 
    retries = _retries_val

    _delay_base_val = settings.summary_llm_retry_delay_base_s
    if not isinstance(_delay_base_val, (int, float)) or _delay_base_val < 0:
        _delay_base_val = settings.enrichment_llm_retry_delay_base_s
    if not isinstance(_delay_base_val, (int, float)) or _delay_base_val < 0:
        _delay_base_val = 2
    retry_delay_base = _delay_base_val

    # *** FIX HERE: Use GenerateContentConfig ***
    generation_config_obj = genai_types.GenerateContentConfig( # Corrected class name
        response_mime_type="application/json",
        temperature=temperature,
        # You can add other relevant GenerateContentConfig parameters here if needed
        # e.g., max_output_tokens=settings.summary_llm_max_tokens if you have such a setting
    )
    
    response_obj = None
    for attempt in range(retries):
        try:
            log.debug(f"Attempt {attempt+1}/{retries} to call Gemini for summary.")
            response_obj = client.models.generate_content(
                model=model_name, 
                contents=prompt, 
                config=generation_config_obj # Pass the correctly typed object
            )
            # Check prompt_feedback AFTER the call, and ensure prompt_feedback itself is not None
            if response_obj.prompt_feedback and response_obj.prompt_feedback.block_reason:
                log.error(f"Summarization prompt blocked. Reason: {response_obj.prompt_feedback.block_reason}")
                raise RuntimeError(f"Summarization prompt blocked by API: {response_obj.prompt_feedback.block_reason}")
            
            log.debug(f"Gemini summary response text (first 100 chars): {response_obj.text[:100]}")
            return response_obj.text
        except Exception as e:
            log.warning(f"Gemini API error (summary) on attempt {attempt+1}/{retries}: {type(e).__name__} - {e}")
            # Check prompt_feedback in exception handling as well
            if response_obj and response_obj.prompt_feedback and response_obj.prompt_feedback.block_reason:
                 log.error(f"Summarization prompt blocked (checked during exception). Reason: {response_obj.prompt_feedback.block_reason}")
                 # Potentially re-raise a more specific error or just let the retry logic handle it unless it's the last attempt
                 # For now, it will fall through to the retry or max retries reached.
            
            if attempt + 1 == retries:
                log.error("Max retries reached for Gemini summary API call.")
                raise # Re-raise the last exception
            time.sleep((2 ** attempt) * retry_delay_base)
            
    # This line should ideally not be reached if retries > 0, as the loop either returns or raises.
    # If retries is 0, then this would be the path taken if the first attempt fails.
    raise RuntimeError("Failed to get response from Gemini after all retries.")

# --- Main Entrypoint ---
# (summarize_day_activities remains largely the same, ensure it uses the fixed invoke function)
def summarize_day_activities(day: date, settings: Settings, force_regenerate: bool = False) -> Path:
    log.info(f"Starting daily summary generation for {day.isoformat()}. Force regenerate: {force_regenerate}")
    source_parquet_path = settings.curated_dir / f"{day}.parquet"
    output_summary_path = settings.summary_dir / f"{day}.json"
    settings.summary_dir.mkdir(parents=True, exist_ok=True)
    summary_llm_cache_dir = settings.summary_llm_cache_dir # Use from settings
    summary_llm_cache_dir.mkdir(parents=True, exist_ok=True)
    llm_response_cache_path = summary_llm_cache_dir / f"{day}.raw_summary.json"

    if output_summary_path.exists() and not force_regenerate:
        log.info(f"Daily summary for {day} already exists at {output_summary_path}. Skipping.")
        return output_summary_path
    if not source_parquet_path.exists():
        log.error(f"Source curated timeline file not found: {source_parquet_path}")
        raise FileNotFoundError(f"Source curated timeline file not found: {source_parquet_path}")
    df_curated = pl.read_parquet(source_parquet_path)
    if df_curated.is_empty():
        log.warning(f"Source curated timeline for {day} is empty. Writing empty summary.")
        empty_stats = Stats(total_active_time_min=0, focus_time_min=0, number_blocks=0)
        empty_summary = DailySummary(date=day, blocks=[], day_summary="No activities recorded.", stats=empty_stats)
        output_summary_path.write_text(empty_summary.model_dump_json(indent=2))
        return output_summary_path
    timeline_entries = []
    for r in df_curated.to_dicts():
        if isinstance(r.get('start'), datetime) and r['start'].tzinfo is None: r['start'] = r['start'].replace(tzinfo=timezone.utc)
        if isinstance(r.get('end'), datetime) and r['end'].tzinfo is None: r['end'] = r['end'].replace(tzinfo=timezone.utc)
        timeline_entries.append(EnrichedTimelineEntry(**r))
    
    gap_seconds_for_grouping = settings.summary_pregroup_gap_s # Use from settings
    pre_grouped_segments = _group_adjacent_entries(timeline_entries, gap_s=gap_seconds_for_grouping)
    if not pre_grouped_segments:
        log.warning(f"No activity segments after pre-grouping for {day}. Writing empty summary.")
        empty_stats = Stats(total_active_time_min=0, focus_time_min=0, number_blocks=0)
        empty_summary = DailySummary(date=day, blocks=[], day_summary="No significant activity segments.", stats=empty_stats)
        output_summary_path.write_text(empty_summary.model_dump_json(indent=2))
        return output_summary_path

    markdown_input_for_llm = _format_groups_for_llm_prompt(pre_grouped_segments, settings)
    llm_prompt = _build_summary_prompt(day.isoformat(), markdown_input_for_llm, settings)
    raw_llm_json_response: Optional[str] = None
    
    # Determine if LLM call for summary should be forced
    force_summary_llm_call = settings.summary_force_llm or force_regenerate

    if llm_response_cache_path.exists() and not force_summary_llm_call:
        log.info(f"Using cached LLM raw response for summary of {day} from {llm_response_cache_path}")
        raw_llm_json_response = llm_response_cache_path.read_text()
    else:
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            msg = "GOOGLE_API_KEY (or GEMINI_API_KEY) not set."
            log.error(msg); raise ValueError(msg)
        try:
            gemini_client = genai.Client(api_key=api_key)
            log.info(f"Querying Gemini for daily summary of {day} (Force LLM: {force_summary_llm_call})...")
            raw_llm_json_response = _invoke_gemini_for_summary(gemini_client, llm_prompt, settings) # Pass full settings
            llm_response_cache_path.write_text(raw_llm_json_response)
            log.info(f"Cached raw LLM summary response to {llm_response_cache_path}")
        except Exception as e:
            log.error(f"Failed to get summary from LLM for {day}: {e}", exc_info=True)
            (summary_llm_cache_dir / f"{day}.error.prompt.txt").write_text(llm_prompt)
            if raw_llm_json_response: (summary_llm_cache_dir / f"{day}.error.response.txt").write_text(raw_llm_json_response)
            raise 
    if not raw_llm_json_response:
        log.error(f"No raw JSON response from LLM for summary of {day}.")
        raise ValueError(f"LLM provided no response for summary of {day}.")
    try:
        parsed_llm_data = json.loads(raw_llm_json_response)
        daily_summary_obj = DailySummary(
            date=day, 
            blocks=[Block(**b) for b in parsed_llm_data.get("blocks", [])],
            day_summary=parsed_llm_data.get("day_summary", "Summary not generated."),
            stats=Stats(**parsed_llm_data.get("stats", {"total_active_time_min":0, "focus_time_min":0, "number_blocks":0})),
            version=DailySummary.model_fields['version'].default
        )
    except Exception as e:
        log.error(f"Failed to parse/validate LLM JSON for summary of {day}: {e}", exc_info=True)
        log.error(f"Problematic summary JSON: {raw_llm_json_response[:500]}...")
        if not (summary_llm_cache_dir / f"{day}.error.response.txt").exists():
            (summary_llm_cache_dir / f"{day}.error.response.txt").write_text(raw_llm_json_response)
        raise
    if EMBED_MODEL and daily_summary_obj.blocks:
        texts_to_embed = [b.summary for b in daily_summary_obj.blocks if b.summary]
        if texts_to_embed:
            try:
                log.info(f"Generating embeddings for {len(texts_to_embed)} block summaries for {day}.")
                embeddings = EMBED_MODEL.encode(texts_to_embed, normalize_embeddings=True).tolist()
                embed_idx = 0
                for block in daily_summary_obj.blocks:
                    if block.summary and embed_idx < len(embeddings):
                        block.embedding = embeddings[embed_idx]; embed_idx += 1
            except Exception as e: log.error(f"Failed to generate embeddings for {day}: {e}", exc_info=True)
    output_summary_path.write_text(daily_summary_obj.model_dump_json(indent=2))
    log.info(f"✅ Daily summary for {day} generated to {output_summary_path}")
    return output_summary_path

# --- CLI helper ---
# (__main__ block remains largely the same, ensure it uses summarize_day_activities and passes settings)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-7s] [%(name)-25s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    from dotenv import load_dotenv
    project_root_for_env = Path(__file__).resolve().parents[2] 
    dotenv_path = project_root_for_env / ".env"
    if dotenv_path.exists(): load_dotenv(dotenv_path=dotenv_path); log.info(f"Loaded .env from {dotenv_path}")
    else: log.warning(f".env not found at {dotenv_path}")
    test_settings = Settings()
    day_to_summarize = date.today() - timedelta(days=1); force_flag = True 
    log.info(f"Running test summarization for: {day_to_summarize}, Force: {force_flag}")
    dummy_curated_dir = test_settings.curated_dir; dummy_curated_dir.mkdir(parents=True, exist_ok=True)
    dummy_curated_file = dummy_curated_dir / f"{day_to_summarize}.parquet"
    if not dummy_curated_file.exists():
        log.warning(f"Dummy file {dummy_curated_file} not found. Creating minimal one.")
        try:
            dummy_data = [ { "start": (datetime.now(timezone.utc) - timedelta(hours=i+1)).isoformat(), "end": (datetime.now(timezone.utc) - timedelta(hours=i, minutes=30)).isoformat(), "app": f"App{i}", "title": f"Title {i}", "url": None, "browser": None, "activity": f"Activity {i}", "project": f"Project {i%2}", "notes": f"Notes {i}"} for i in range(2)]
            df_dummy = pl.from_dicts(dummy_data).with_columns([ pl.col("start").str.to_datetime().dt.replace_time_zone("UTC"), pl.col("end").str.to_datetime().dt.replace_time_zone("UTC"), pl.all().exclude(["start", "end"]).cast(pl.Utf8) ])
            df_dummy.write_parquet(dummy_curated_file)
            log.info(f"Created dummy file: {dummy_curated_file}")
        except Exception as e_dummy: log.error(f"Could not create dummy file: {e_dummy}", exc_info=True); exit(1)
    try:
        result_path = summarize_day_activities(day_to_summarize, test_settings, force_regenerate=force_flag)
        if result_path: log.info(f"Test success. Output: {result_path}\n{result_path.read_text()}")
        else: log.error(f"Test failed for {day_to_summarize}.")
    except FileNotFoundError: log.error(f"Ensure source file exists for {day_to_summarize}.")
    except Exception as e: log.error(f"Error in test summarization: {e}", exc_info=True)
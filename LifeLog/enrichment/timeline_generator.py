from __future__ import annotations
from datetime import date, datetime, timedelta, timezone, time
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
import logging
import os
import sys
from pydantic import BaseModel, Field, field_validator, model_validator, RootModel
import uuid
import google.generativeai as genai
from google.generativeai import types as genai_types
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
        conn.execute("BEGIN TRANSACTION")
        cur = conn.cursor()
        try:
            for e in enriched_entries:
                cur.execute(
                    "UPDATE timeline_events SET category = ?, notes = ?, project = ?, last_modified = CURRENT_TIMESTAMP WHERE event_id = ?",
                    (e.activity, e.notes, e.project, uuid.UUID(e.event_id)),
                )
            conn.commit()
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
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
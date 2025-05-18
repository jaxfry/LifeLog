from __future__ import annotations
import logging
"""LifeLog ‒ ActivityWatch enrichment layer"""

# ── Monkey‑patch HTTPX to allow unicode & bytes in header values ───────────
_httpx_patch_logger = logging.getLogger(__name__ + ".httpx_patch")
try:
    import httpx._models as _httpx_models
    from httpx._types import HeaderTypes as _HeaderTypes 

    _original_normalize_header_value = _httpx_models._normalize_header_value

    def _patched_normalize_header_value(value: _HeaderTypes) -> bytes: # type: ignore[name-defined]
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        if isinstance(value, str):
            try:
                return value.encode("ascii")
            except UnicodeEncodeError:
                return value.encode("utf-8", errors="ignore")
        _httpx_patch_logger.error(f"Unexpected header value type: {type(value)}. Expected str or bytes.")
        raise TypeError(f"Unexpected header value type: {type(value)}. Expected str or bytes.")

    _httpx_models._normalize_header_value = _patched_normalize_header_value  # type: ignore[misc]
    _httpx_patch_logger.debug("Successfully monkey-patched httpx._models._normalize_header_value.")

except ImportError:  # pragma: no cover
    _httpx_patch_logger.debug("httpx not installed or _models not found, skipping patch.")
except AttributeError: # pragma: no cover
    _httpx_patch_logger.warning(
        "Failed to monkey-patch httpx._models._normalize_header_value. "
        "The function might have been removed, renamed, or httpx is not fully available."
    )

import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import List # Python < 3.9 compatibility, otherwise use list

import polars as pl
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
# Load environment variables from .env file if present
load_dotenv()

# --- LifeLog Specific Imports ---
# Ensure these paths are correct for your project structure
try:
    from LifeLog.config import Settings
    from LifeLog.models import TimelineEntry
    from LifeLog.enrichment.project_resolver import ProjectResolver
except ImportError as e:
    print(f"Critical Import Error: {e}. Please ensure LifeLog modules are in PYTHONPATH.")
    sys.exit(1)
# --- End LifeLog Specific Imports ---

logger = logging.getLogger(__name__)

ST = Settings()
_local_tz_name = getattr(ST, 'local_timezone_name', "America/Vancouver")
try:
    LOCAL_TZ = ZoneInfo(_local_tz_name)
except Exception:
    logger.exception(f"Failed to load timezone '{_local_tz_name}', defaulting to UTC.")
    LOCAL_TZ = timezone.utc


TOKEN_MARGIN = getattr(ST, 'token_margin', 0.30) # Default 30% margin

if hasattr(ST, 'gemini_api_key') and ST.gemini_api_key:
    try:
        genai.configure(api_key=ST.gemini_api_key)
        logger.info("Gemini API key configured from settings.")
    except Exception as e:
        logger.error(f"Failed to configure Gemini API key from settings: {e}")
elif not os.getenv("GOOGLE_API_KEY"):
    logger.warning(
        "Gemini API key not found in settings (ST.gemini_api_key) or environment (GOOGLE_API_KEY). "
        "Gemini calls may fail if the environment is not otherwise configured for authentication."
    )

# ── Project‑alias helpers ─────────────────────────────────────────────────

@lru_cache
def _project_aliases() -> dict[str, str]:
    cfg_path = ST.assets_dir / "project_aliases.yaml"
    if not cfg_path.exists():
        logger.info("Project alias file not found at %s. No aliases will be applied.", cfg_path)
        return {}
    try:
        import yaml
        aliases = yaml.safe_load(cfg_path.read_text())
        if aliases is None: return {}
        if not isinstance(aliases, dict):
            logger.warning("Project alias file %s does not contain a valid dictionary. Skipping.", cfg_path)
            return {}
        return {str(k): str(v) for k, v in aliases.items()}
    except ImportError: # pragma: no cover
        logger.warning("PyYAML not installed. Project aliases cannot be loaded. To use aliases, run: pip install PyYAML")
        return {}
    except Exception as exc:  # pragma: no cover
        logger.warning("Project alias file %s unreadable or malformed – skipping (%s)", cfg_path, exc)
        return {}

# ── Raw‑event loading & pre‑cleaning ──────────────────────────────────────

def _load_events(day: date) -> pl.DataFrame:
    raw_path = ST.raw_dir / f"{day}.parquet"
    if not raw_path.exists():
        raise FileNotFoundError(f"No raw ActivityWatch data for {day} at {raw_path}")

    df = pl.read_parquet(raw_path)
    if df.height == 0:
        logger.info("Raw event file for %s is empty.", day)
        return df

    min_duration = getattr(ST, 'min_duration_ms', 1000)
    df = df.filter(pl.col("duration") >= min_duration)

    if getattr(ST, 'drop_idle', True):
        idle_keywords = getattr(ST, 'idle_keywords', ["idle", "afk"])
        if idle_keywords:
            idle_pattern = "|".join(map(re.escape, idle_keywords))
            df = df.filter(~pl.col("app").str.to_lowercase().str.contains(idle_pattern))

    if df.height == 0:
        logger.info("No events remaining after basic pruning for %s.", day)
        return df

    df = df.with_columns(
        pl.col("timestamp")
        .cast(pl.Int64)
        .cast(pl.Datetime("ms", time_zone="UTC"))
        .alias("timestamp_utc")
    ).sort("timestamp_utc")

    logger.info("🔍 Raw events loaded and pre-cleaned for %s (UTC): %d", day, df.height)
    return df

# ── Prompt Template Details ───────────────────────────────────────────────

@lru_cache
def _get_prompt_template_details(model_name: str, day_str: str, template_str: str) -> tuple[genai.GenerativeModel, int, int]:
    model = genai.GenerativeModel(model_name)
    base_prompt_content = template_str.format(day=day_str, events_md="", local_tz_name=LOCAL_TZ.key)
    try:
        token_count_response = model.count_tokens(base_prompt_content)
        template_tokens = token_count_response.total_tokens
    except Exception as e:
        logger.error(f"Failed to count tokens for prompt template with model {model_name}: {e}. Using fallback estimate.", exc_info=True)
        template_tokens = len(base_prompt_content) // 3
    
    max_prompt_tokens_setting = getattr(ST, 'max_prompt_tokens', 8000) # User-defined total tokens
    logger.info(
        f"ST.max_prompt_tokens is set to: {max_prompt_tokens_setting}. "
        f"Ensure this is appropriate for model '{model_name}'."
    )
    max_tokens_for_full_prompt = int(max_prompt_tokens_setting * (1.0 - TOKEN_MARGIN))

    if template_tokens >= max_tokens_for_full_prompt:
       logger.error(
           f"Base prompt template alone ({template_tokens} tokens) exceeds or meets the "
           f"effective max prompt token limit ({max_tokens_for_full_prompt} tokens derived from "
           f"ST.max_prompt_tokens={max_prompt_tokens_setting} and TOKEN_MARGIN={TOKEN_MARGIN}). "
           "Increase ST.max_prompt_tokens or shorten the prompt template."
        )
       raise ValueError("Prompt template too large for configured token limits.")
    return model, template_tokens, max_tokens_for_full_prompt

# ── Events to Markdown ────────────────────────────────────────────────────

def _events_to_md(df: pl.DataFrame) -> str:
    if df.height == 0:
        return "(No events in this chunk)"
    pretty_df = df.with_columns(
        pl.col("timestamp_utc")
        .dt.convert_time_zone(LOCAL_TZ.key)
        .dt.strftime("%H:%M:%S")
        .alias("time_local")
    ).select("time_local", "duration", "app", "title")
    return pretty_df.to_pandas().to_markdown(index=False)

# ── Prompt Template ───────────────────────────────────────────────────────

_JSON_TIMELINE_PROMPT_TEMPLATE = (
    "You are a personal life‑logging assistant. Convert the raw events below into "
    "concise JSON timeline entries. Follow the *exact* schema provided. "
    "Respond **only** with a single JSON array of objects. Do **not** use markdown "
    "fences (like ```json ... ```) or any other surrounding prose or explanations.\n\n"
    "JSON Schema (array of objects):\n"
    "[{{\"start\": \"YYYY-MM-DDTHH:MM:SSZ\", \"end\": \"YYYY-MM-DDTHH:MM:SSZ\", "
    "\"activity\": \"string - concise summary of the event\", "
    "\"project\": \"string - associated project, or empty string if none, or null if not applicable\", "
    "\"location\": \"string - optional location context, or empty string/null\", "
    "\"notes\": \"string - brief additional details or raw title if relevant, empty string if none\"}}]\n\n"
    "Key Instructions:\n"
    "* Timestamps: All `start` and `end` timestamps MUST be in UTC (ending with 'Z') "
    "and fall on the specified UTC date: {day}.\n"
    "* Merging: Combine adjacent raw events if they represent the same continuous activity and project.\n"
    "* Chronology: Entries must be strictly chronological by `start` time.\n"
    "* Conciseness: Be brief and to the point for `activity` and `notes`.\n"
    "* Empty/Null: Use empty strings or null for optional fields if no data is applicable.\n"
    "* Completeness: Process all provided raw events into timeline entries.\n\n"
    "Raw Events (local time zone: {local_tz_name}, UTC date: {day}):\n\n{events_md}\n"
)

# ── Gemini call helper ────────────────────────────────────────────────────

def _call_gemini(prompt: str, model: genai.GenerativeModel, *, retries: int = 3) -> str:
    temperature_setting = float(getattr(ST, 'temperature', 0.2))
    generation_config = GenerationConfig(
        temperature=temperature_setting,
        response_mime_type="application/json"
    )
    last_exception = None
    for attempt in range(1, retries + 1):
        try:
            response = model.generate_content(prompt, generation_config=generation_config)
            if not response.candidates:
                logger.warning("Gemini response has no candidates (attempt %d/%d). Prompt length: %d chars.", attempt, retries, len(prompt))
                if attempt == retries: raise ValueError(f"Gemini response has no candidates after {retries} retries.")
                time.sleep((2 ** attempt) + (time.time_ns() % 1000 / 1000.0))
                continue

            if response.text: return response.text
            
            content_parts = response.candidates[0].content.parts
            text_segments = [p.text for p in content_parts if hasattr(p, "text") and p.text is not None]
            if not text_segments:
                logger.warning("Gemini response parts contain no text (attempt %d/%d). Parts: %s", attempt, retries, content_parts)
                if attempt == retries: raise ValueError(f"Gemini response parts contained no text after {retries} retries.")
                time.sleep((2 ** attempt) + (time.time_ns() % 1000 / 1000.0))
                continue
            return "".join(text_segments)
        except Exception as exc:
            last_exception = exc
            logger.warning("Gemini API call failed (attempt %d/%d): %s. Prompt length: %d chars.", attempt, retries, exc, len(prompt))
            if attempt == retries:
                logger.error("Gemini API call failed after %d retries.", retries)
                raise
            time.sleep((2 ** attempt) + (time.time_ns() % 1000 / 1000.0))
    
    if last_exception: raise last_exception # type: ignore
    raise RuntimeError("Gemini call helper exited loop unexpectedly.")

# ── JSON extraction ───────────────────────────────────────────────────────

def _extract_json(text_content: str) -> list[dict]:
    extracted_objects: list[dict] = []
    try:
        data = json.loads(text_content)
        if isinstance(data, list):
            if all(isinstance(item, dict) for item in data): extracted_objects.extend(data)
        elif isinstance(data, dict): extracted_objects.append(data)
        if extracted_objects: return extracted_objects
    except json.JSONDecodeError:
        logger.debug("Entire response is not valid JSON. Trying regex. Content: %s", text_content[:200])
    except Exception as e:
        logger.warning("Unexpected error parsing entire response as JSON: %s. Content: %s", e, text_content[:200])

    for match in re.finditer(r"```(?:json)?\s*(\[.*?\])\s*```", text_content, re.DOTALL | re.IGNORECASE):
        try:
            json_str = match.group(1)
            data = json.loads(json_str)
            if isinstance(data, list) and all(isinstance(item, dict) for item in data):
                extracted_objects.extend(data)
            if extracted_objects: break 
        except json.JSONDecodeError: pass
    
    if not extracted_objects:
        for match in re.finditer(r"^\s*(\[.*\])\s*$", text_content, re.DOTALL):
            try:
                json_str = match.group(1)
                data = json.loads(json_str)
                if isinstance(data, list) and all(isinstance(item, dict) for item in data):
                    extracted_objects.extend(data)
                if extracted_objects: break 
            except json.JSONDecodeError: pass
    
    if not extracted_objects:
        logger.warning("Could not extract any valid JSON list of objects. Response: %s", text_content[:500])
    return extracted_objects

# ── Entry post‑processing helpers ─────────────────────────────────────────

def _fix_entries(raw_json_objects: list[dict], target_day: date) -> list[TimelineEntry]:
    valid_entries: list[TimelineEntry] = []
    day_start_utc = datetime.combine(target_day, datetime.min.time(), tzinfo=timezone.utc)
    day_end_utc = day_start_utc + timedelta(days=1)

    for i, obj in enumerate(raw_json_objects):
        try:
            if not isinstance(obj, dict) or not all(k in obj for k in ["start", "end", "activity"]):
                logger.debug("Skipping item %d: Not a dict or missing required fields: %s", i, obj)
                continue

            s_str, e_str = obj["start"], obj["end"]
            start_dt = datetime.fromisoformat(str(s_str).replace("Z", "+00:00")).astimezone(timezone.utc)
            end_dt = datetime.fromisoformat(str(e_str).replace("Z", "+00:00")).astimezone(timezone.utc)

            if not (day_start_utc <= start_dt < day_end_utc and start_dt < end_dt):
                logger.debug("Skipping entry %d: Timestamp issue. Start: %s, End: %s, Day: %s. Obj: %s", i, start_dt, end_dt, target_day, obj)
                continue
            
            entry_data = {
                "start": start_dt, "end": end_dt,
                "activity": str(obj.get("activity", "")),
                "project": str(p) if (p := obj.get("project")) is not None else None,
                "location": str(l) if (l := obj.get("location")) is not None else None,
                "notes": str(obj.get("notes", "")),
            }
            valid_entries.append(TimelineEntry(**entry_data))
        except (ValueError, TypeError) as exc:
            logger.debug("Skipping malformed entry %d (%s): %s. Object: %s", i, type(exc).__name__, exc, obj)
        except Exception as exc:
            logger.warning("Unexpected error processing entry %d: %s. Object: %s", i, exc, obj, exc_info=True)
    return valid_entries

def _apply_project_aliases(entries: list[TimelineEntry]) -> None:
    aliases = _project_aliases()
    if not aliases: return
    for entry in entries:
        if entry.project and entry.project in aliases:
            entry.project = aliases[entry.project]

def _merge_adjacent(entries: list[TimelineEntry], max_gap_seconds: int = 15) -> list[TimelineEntry]:
    if not entries: return []
    entries.sort(key=lambda e: (e.start, e.end))
    merged_list: list[TimelineEntry] = [entries[0]]
    for current_entry in entries[1:]:
        last_merged = merged_list[-1]
        if (current_entry.activity == last_merged.activity and
            current_entry.project == last_merged.project and
            (current_entry.start - last_merged.end).total_seconds() <= max_gap_seconds):
            last_merged.end = max(last_merged.end, current_entry.end)
        else:
            merged_list.append(current_entry)
    return merged_list

# ── Public API ────────────────────────────────────────────────────────────

def enrich(day: date | str, *, force: bool = False) -> Path:
    if isinstance(day, str):
        try: day_obj = date.fromisoformat(day)
        except ValueError:
            logger.error(f"Invalid date string format: '{day}'. Please use YYYY-MM-DD.")
            raise
    else: day_obj = day
    day_str = day_obj.isoformat()

    ST.cache_dir.mkdir(parents=True, exist_ok=True)
    ST.curated_dir.mkdir(parents=True, exist_ok=True)
    out_file = ST.curated_dir / f"{day_str}.parquet"
    
    # Attempt to get schema for empty DataFrames
    empty_df_schema = None
    if hasattr(TimelineEntry, 'polars_schema') and callable(TimelineEntry.polars_schema):
        try:
            empty_df_schema = TimelineEntry.polars_schema()
        except Exception as e:
            logger.warning(f"Could not retrieve polars_schema from TimelineEntry: {e}")


    raw_path = ST.raw_dir / f"{day_str}.parquet"
    if not raw_path.exists() or force:
        logger.info("🔄 Ingesting raw data for %s (force=%s, exists=%s)", day_str, force, raw_path.exists())
        try:
            from LifeLog.ingestion.activitywatch import ingest 
            ingest(day_obj)
        except ImportError:
            logger.error("Failed to import LifeLog.ingestion.activitywatch.ingest.", exc_info=True)
            if not raw_path.exists(): raise FileNotFoundError(f"Ingestion import failed and raw data not found: {raw_path}")
        except Exception as e:
            logger.error(f"Error during raw data ingestion for {day_str}: {e}", exc_info=True)
            if force or not raw_path.exists(): raise RuntimeError(f"Forced/initial ingestion failed for {day_str}") from e

    try:
        df_raw_events = _load_events(day_obj)
    except FileNotFoundError:
        logger.error(f"No raw ActivityWatch data for {day_str} at {raw_path}. Cannot proceed.")
        pl.DataFrame(schema=empty_df_schema).write_parquet(out_file)
        return out_file

    if df_raw_events.height == 0:
        logger.warning("⚠️ No events to process for %s after loading/pruning.", day_str)
        pl.DataFrame(schema=empty_df_schema).write_parquet(out_file)
        return out_file

    try:
        model_name = getattr(ST, 'model_name', 'gemini-1.5-flash-latest') # Updated default
        model, template_tokens, max_tokens_for_full_prompt = _get_prompt_template_details(
            model_name, day_str, _JSON_TIMELINE_PROMPT_TEMPLATE
        )
        logger.info(
            f"Using model '{model_name}'. Prompt template overhead: {template_tokens} tokens. "
            f"Max tokens for full prompt (after margin): {max_tokens_for_full_prompt}."
        )
    except Exception as e:
        logger.error(f"Failed to initialize Gemini model or count template tokens: {e}. Cannot proceed.", exc_info=True)
        pl.DataFrame(schema=empty_df_schema).write_parquet(out_file)
        raise RuntimeError(f"Gemini model setup failed for {model_name}") from e

    all_extracted_entries: list[TimelineEntry] = []
    processed_rows_count = 0
    chunk_idx = 0
    CHARS_PER_TOKEN_HEURISTIC = getattr(ST, 'chars_per_token_heuristic', 3.5)
    max_md_chars_for_events = int((max_tokens_for_full_prompt - template_tokens) * CHARS_PER_TOKEN_HEURISTIC)

    if max_md_chars_for_events <= 0:
        logger.error(
            f"Calculated max_md_chars_for_events is {max_md_chars_for_events}. "
            f"Template tokens ({template_tokens}) too high relative to max_tokens_for_full_prompt ({max_tokens_for_full_prompt})."
        )
        pl.DataFrame(schema=empty_df_schema).write_parquet(out_file)
        return out_file
    logger.info(f"Max character length for events Markdown (heuristic): {max_md_chars_for_events}")

    while processed_rows_count < df_raw_events.height:
        chunk_idx += 1
        current_chunk_event_dfs: list[pl.DataFrame] = []
        current_events_md_for_chunk = ""
        
        for event_offset in range(df_raw_events.height - processed_rows_count):
            absolute_event_index = processed_rows_count + event_offset
            event_to_add_df = df_raw_events.slice(absolute_event_index, 1)
            md_for_single_event_to_add = _events_to_md(event_to_add_df)

            prospective_events_md = (current_events_md_for_chunk + "\n" + md_for_single_event_to_add 
                                     if current_events_md_for_chunk else md_for_single_event_to_add)
            
            if len(prospective_events_md) > max_md_chars_for_events and current_chunk_event_dfs:
                logger.debug(f"Chunk full by char heuristic ({len(prospective_events_md)} > {max_md_chars_for_events}). Finalizing with {len(current_events_md_for_chunk)} chars.")
                break 

            prospective_full_prompt = _JSON_TIMELINE_PROMPT_TEMPLATE.format(
                day=day_str, events_md=prospective_events_md, local_tz_name=LOCAL_TZ.key
            )
            
            try:
                prospective_total_tokens = model.count_tokens(prospective_full_prompt).total_tokens
            except Exception as e:
                logger.warning(f"Token counting failed for prospective chunk (prompt len {len(prospective_full_prompt)} chars): {e}.")
                if current_chunk_event_dfs:
                    logger.info("Finalizing chunk with previously accumulated events due to token count failure.")
                    break
                else:
                    logger.error(f"Token counting failed for first event of chunk (raw index {absolute_event_index}). Skipping event.")
                    processed_rows_count += 1 
                    current_chunk_event_dfs = [] # Ensure this attempt leads to an empty chunk being skipped
                    break 

            if prospective_total_tokens > max_tokens_for_full_prompt:
                if current_chunk_event_dfs:
                    logger.debug(f"Chunk full by token count ({prospective_total_tokens} > {max_tokens_for_full_prompt}). Finalizing.")
                    break
                else:
                    logger.warning(
                        f"Single event (raw index {absolute_event_index}) makes prompt {prospective_total_tokens} tokens "
                        f"(limit {max_tokens_for_full_prompt}). Prompt chars: {len(prospective_full_prompt)}. Processing alone."
                    )
                    current_chunk_event_dfs.append(event_to_add_df)
                    current_events_md_for_chunk = prospective_events_md 
                    break 
            
            current_chunk_event_dfs.append(event_to_add_df)
            current_events_md_for_chunk = prospective_events_md

        if not current_chunk_event_dfs:
            if processed_rows_count >= df_raw_events.height: logger.info("All events processed or skipped.")
            else: logger.debug(f"No events collected for chunk {chunk_idx}, continuing.")
            continue

        chunk_df = pl.concat(current_chunk_event_dfs)
        final_events_md_for_this_chunk = current_events_md_for_chunk 

        logger.info(
            f"🪄 Processing chunk {chunk_idx} with {chunk_df.height} events "
            f"(MD length {len(final_events_md_for_this_chunk)} chars) for {day_str}."
        )

        chunk_cache_file = ST.cache_dir / f"{day_str}_chunk_{chunk_idx:02d}_llm_response.txt"
        raw_llm_response_text = ""

        if chunk_cache_file.exists() and not force:
            logger.info("♻️ Using cached LLM response for chunk %d: %s", chunk_idx, chunk_cache_file)
            raw_llm_response_text = chunk_cache_file.read_text()
        else:
            final_prompt_for_llm = _JSON_TIMELINE_PROMPT_TEMPLATE.format(
                day=day_str, events_md=final_events_md_for_this_chunk, local_tz_name=LOCAL_TZ.key
            )
            try: # Log final token count
                final_token_count = model.count_tokens(final_prompt_for_llm).total_tokens
                logger.info(f"Chunk {chunk_idx} final prompt: {final_token_count} tokens, {len(final_prompt_for_llm)} chars.")
                if final_token_count > max_tokens_for_full_prompt:
                    logger.warning(f"  🚨 Chunk {chunk_idx} prompt ({final_token_count} tokens) EXCEEDS limit ({max_tokens_for_full_prompt}). API call may fail.")
            except Exception as e: logger.warning(f"Could not count tokens for final prompt of chunk {chunk_idx}: {e}")

            try:
                raw_llm_response_text = _call_gemini(final_prompt_for_llm, model)
                if raw_llm_response_text.strip():
                    chunk_cache_file.write_text(raw_llm_response_text)
                    logger.info("💾 Cached LLM response for chunk %d → %s", chunk_idx, chunk_cache_file)
                else: logger.warning("LLM call for chunk %d returned empty. No cache written.", chunk_idx)
            except Exception as e:
                logger.error(f"Error calling Gemini for chunk {chunk_idx} of {day_str}: {e}", exc_info=False)
                if chunk_cache_file.exists() and not force:
                    logger.warning(f"Falling back to cache {chunk_cache_file} for chunk {chunk_idx} due to API error.")
                    raw_llm_response_text = chunk_cache_file.read_text()
                else:
                    logger.error(f"No cache for chunk {chunk_idx} after API error. Chunk skipped.")
                    processed_rows_count += chunk_df.height
                    continue

        if raw_llm_response_text.strip():
            json_objects = _extract_json(raw_llm_response_text)
            chunk_entries = _fix_entries(json_objects, day_obj)
            logger.info("➡️ Extracted %d valid entries from LLM response for chunk %d.", len(chunk_entries), chunk_idx)
            all_extracted_entries.extend(chunk_entries)
        else:
            logger.warning("LLM response for chunk %d is empty. Skipping post-processing.", chunk_idx)
        
        processed_rows_count += chunk_df.height

    if not all_extracted_entries:
        logger.warning("🚫 No valid timeline entries extracted from any chunk for %s.", day_str)
        pl.DataFrame(schema=empty_df_schema).write_parquet(out_file)
        return out_file

    logger.info("🛠️ Post-processing %d extracted entries...", len(all_extracted_entries))
    try:
        resolver = ProjectResolver() 
        for entry in all_extracted_entries:
            if entry.project or (entry.notes and entry.notes.strip()):
                resolved_project = resolver.resolve(entry.project, context=entry.notes)
                if resolved_project and resolved_project != entry.project: entry.project = resolved_project
    except Exception as e:
        logger.error(f"Error during project resolution: {e}. Proceeding partially.", exc_info=True)

    _apply_project_aliases(all_extracted_entries)
    merge_gap_sec = getattr(ST, 'merge_gap_seconds', 15)
    merged_entries = _merge_adjacent(all_extracted_entries, max_gap_seconds=merge_gap_sec)
    logger.info("🖇️ Merged entries from %d to %d (gap_sec=%d).", len(all_extracted_entries), len(merged_entries), merge_gap_sec)

    min_final_duration_sec = getattr(ST, 'min_final_duration_seconds', 15)
    final_entries = [e for e in merged_entries if (e.end - e.start).total_seconds() >= min_final_duration_sec]
    logger.info("🗑️ Pruned short entries (min_duration=%ds), %d remaining.", min_final_duration_sec, len(final_entries))

    if not final_entries:
        logger.warning("🏁 No entries remaining after final pruning for %s.", day_str)
        pl.DataFrame(schema=empty_df_schema).write_parquet(out_file)
        return out_file
        
    try:
        output_data = [e.model_dump(mode='python') for e in final_entries]
        output_df = pl.DataFrame(output_data, schema_overrides=empty_df_schema or None)
    except AttributeError: 
        logger.debug("TimelineEntry has no model_dump; using vars().")
        output_df = pl.DataFrame([vars(e) for e in final_entries], schema=empty_df_schema or None)

    output_df.write_parquet(out_file)
    logger.info("✅ Enriched %d timeline entries saved to %s", len(final_entries), out_file)
    return out_file

# ── CLI entrypoint ────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    import argparse
    yesterday = (datetime.now(LOCAL_TZ).date() - timedelta(days=1))
    
    parser = argparse.ArgumentParser(description="Enrich ActivityWatch events for LifeLog using Gemini.")
    parser.add_argument(
        "--day", default=yesterday.isoformat(),
        help=f"Target day (YYYY-MM-DD, default: {yesterday.isoformat()})."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force re-ingestion and re-query Gemini, ignoring caches."
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable DEBUG level logging."
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        for handler in logging.getLogger().handlers: handler.setLevel(logging.DEBUG)
        logger.info("Verbose (DEBUG) logging enabled.")

    try:
        logger.info(f"Starting LifeLog enrichment for day: {args.day}, Force: {args.force}")
        output_file = enrich(args.day, force=args.force)
        logger.info(f"Enrichment process completed successfully. Output: {output_file}")
        sys.exit(0)
    except FileNotFoundError as e:
        logger.critical(f"❌ Enrichment failed: A required file was not found. {e}")
        sys.exit(2)
    except RuntimeError as e:
        logger.critical(f"❌ Enrichment failed due to a critical runtime error: {e}", exc_info=args.verbose)
        sys.exit(3)
    except Exception as exc:
        logger.critical(f"❌ Enrichment failed with an unexpected error: {exc}", exc_info=args.verbose)
        sys.exit(1)
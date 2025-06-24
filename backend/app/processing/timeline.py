"""
Timeline processing module for LifeLog.

This module processes pending events into enriched timeline entries using LLM-based analysis.
It's adapted from the original timeline generator but redesigned for the new database architecture.
"""

import asyncio
import hashlib
import logging
import os
import json
from datetime import datetime, timezone, timedelta, date, time
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from pathlib import Path

import polars as pl
import duckdb
from pydantic import BaseModel, Field, field_validator, model_validator
from google import genai
from google.genai import types as genai_types
from zoneinfo import ZoneInfo

from backend.app.core.settings import Settings
from backend.app.processing import prompts
from backend.app.processing.project_resolver import ProjectResolver
from backend.app.core.utils import with_db_write_retry

log = logging.getLogger(__name__)

# Constants
TIMELINE_SOURCE = "timeline_processor"
PROCESSING_CHUNK_SIZE = 1000
DEFAULT_IDLE_ACTIVITY = "Idle / Away"

@dataclass
class ProcessingWindow:
    """Represents a time window for processing events."""
    start_time: datetime
    end_time: datetime
    local_day: date


class TimelineEntry(BaseModel):
    """Pydantic model for timeline entries returned by LLM."""
    start: datetime = Field(description="Start time UTC ISO format.")
    end: datetime = Field(description="End time UTC ISO format.")
    activity: str = Field(description="Short descriptive activity phrase.")
    project: Optional[str] = Field(default=None, description="Project/course name.")
    notes: Optional[str] = Field(default=None, description="1-2 sentence summary.")

    @field_validator('start', 'end', mode='before')
    @classmethod
    def parse_datetime_utc(cls, v):
        if isinstance(v, str):
            dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
            return dt.astimezone(timezone.utc)
        if isinstance(v, datetime):
            return v.astimezone(timezone.utc)
        raise ValueError("Invalid datetime format")

    @model_validator(mode='after')
    def check_start_before_end(self):
        if self.start and self.end:
            if self.start > self.end:
                log.warning(f"Start time {self.start} is after end time {self.end}. Swapping them.")
                self.start, self.end = self.end, self.start
            if self.start == self.end:
                self.end = self.start + timedelta(seconds=1)
        return self


class LLMResponseCache:
    """Manages caching of LLM responses for testing/development mode."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache_enabled = settings.ENABLE_LLM_CACHE
        self.cache_dir = settings.CACHE_DIR

        if self.cache_enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            log.info(f"LLM cache enabled, using directory: {self.cache_dir}")
        else:
            log.info("LLM cache disabled")

    def _generate_cache_key(self, events_df_chunk: pl.DataFrame, local_day: date) -> str:
        if events_df_chunk.is_empty():
            return f"empty_{local_day.isoformat()}"
        data_str = (
            events_df_chunk
            .select(["time_display", "duration_s", "app", "title", "url"])
            .fill_null("")
            .to_pandas()
            .to_string()
        )
        data_hash = hashlib.md5(data_str.encode()).hexdigest()
        return f"{local_day.isoformat()}_{data_hash}"

    def get_cached_response(self, cache_key: str) -> Optional[List[TimelineEntry]]:
        if not self.cache_enabled:
            return None
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None
        try:
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age > timedelta(hours=self.settings.CACHE_TTL_HOURS):
                log.debug(f"Cache expired for key {cache_key}, removing")
                cache_file.unlink()
                return None
            with open(cache_file, 'r') as f:
                cached_data = json.load(f)
            log.info(f"Using cached LLM response for key {cache_key}")
            return [TimelineEntry.model_validate(entry) for entry in cached_data]
        except Exception as e:
            log.warning(f"Failed to load cache for key {cache_key}: {e}")
            if cache_file.exists():
                cache_file.unlink()
            return None

    def save_to_cache(self, cache_key: str, entries: List[TimelineEntry]) -> None:
        if not self.cache_enabled:
            return
        try:
            cache_file = self.cache_dir / f"{cache_key}.json"
            entries_data = [entry.model_dump(mode='json') for entry in entries]
            with open(cache_file, 'w') as f:
                json.dump(entries_data, f, indent=2)
            log.debug(f"Saved LLM response to cache with key {cache_key}")
        except Exception as e:
            log.warning(f"Failed to save to cache for key {cache_key}: {e}")


class EventAggregator:
    """Aggregates and prepares events for LLM processing."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def aggregate_events(self, events: List[Dict[str, Any]]) -> pl.DataFrame:
        if not events:
            return pl.DataFrame()
        df = pl.from_dicts(events)
        if "start_time" not in df.columns or "end_time" not in df.columns:
            log.error("DataFrame is missing 'start_time' or 'end_time' columns.")
            return pl.DataFrame()
        df = df.with_columns(
            ((pl.col("end_time") - pl.col("start_time")).dt.total_seconds()).alias("duration_s")
        )
        df_activities = df.filter(pl.col("app") != self.settings.AFK_APP_NAME)
        if df_activities.is_empty():
            log.info("No non-AFK activities in this chunk.")
            return pl.DataFrame()
        if self.settings.ENRICHMENT_MIN_DURATION_S > 0:
            df_activities = df_activities.filter(pl.col("duration_s") >= self.settings.ENRICHMENT_MIN_DURATION_S)
        if df_activities.is_empty():
            log.info("No activities remaining after duration filter.")
            return pl.DataFrame()
        truncate_limit = self.settings.ENRICHMENT_PROMPT_TRUNCATE_LIMIT
        ellipsis_suffix = "…"
        df_for_prompt = df_activities.sort("start_time").with_columns([
            pl.col("start_time").dt.strftime("%H:%M:%S").alias("time_display"),
            pl.col("duration_s").round(0).cast(pl.Int32),
            pl.when(pl.col("title").fill_null("").str.len_chars() > truncate_limit)
              .then(pl.col("title").fill_null("").str.slice(0, truncate_limit) + pl.lit(ellipsis_suffix))
              .otherwise(pl.col("title").fill_null(""))
              .alias("title"),
            pl.when(pl.col("url").fill_null("").str.len_chars() > truncate_limit)
              .then(pl.col("url").fill_null("").str.slice(0, truncate_limit) + pl.lit(ellipsis_suffix))
              .otherwise(pl.col("url").fill_null(""))
              .alias("url"),
        ])
        log.info(f"Prepared {df_for_prompt.height} activity events for LLM prompt after filtering.")
        return df_for_prompt


class LLMProcessor:
    """Handles LLM-based timeline enrichment."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = None
        self.cache = LLMResponseCache(settings)
        self._initialize_client()

    #+ REVERTED: This method is now identical to your original working code.
    def _initialize_client(self):
        """Initialize the Gemini client."""
        try:
            api_key = os.getenv("GEMINI_API_KEY") or self.settings.GEMINI_API_KEY
            if not api_key or api_key == "YOUR_API_KEY_HERE":
                raise ValueError("GEMINI_API_KEY not configured")
            self.client = genai.Client(api_key=api_key)
            # This line serves as a connection test.
            self.client.models.list()
            log.info("Gemini client initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize Gemini client: {e}")
            self.client = None

    def _build_prompt(self, events_df_chunk: pl.DataFrame, local_day: date) -> str:
        if events_df_chunk.is_empty():
            return ""
        required_cols = ["time_display", "duration_s", "app", "title", "url"]
        missing_cols = [
            pl.lit("", dtype=pl.Utf8).alias(col)
            for col in required_cols
            if col not in events_df_chunk.columns
        ]
        if missing_cols:
            events_df_chunk = events_df_chunk.with_columns(missing_cols)
        events_table_md = (
            events_df_chunk.select(required_cols)
            .fill_null("")
            .to_pandas()
            .to_markdown(index=False)
        )
        schema_description = (
            '[{"start": "YYYY-MM-DDTHH:MM:SSZ", '
            '"end": "YYYY-MM-DDTHH:MM:SSZ", '
            '"activity": "string", '
            '"project": "string | null", '
            '"notes": "string | null"}]'
        )
        prompt = prompts.TIMELINE_ENRICHMENT_SYSTEM_PROMPT.format(
            day_iso=local_day.isoformat(),
            schema_description=schema_description,
            events_table_md=events_table_md
        )
        return prompt

    #+ REVERTED: This is now the original synchronous implementation.
    def process_chunk_with_llm(self, events_df_chunk: pl.DataFrame, local_day: date) -> List[TimelineEntry]:
        if events_df_chunk.is_empty():
            return []

        if not self.client:
            log.error("Gemini client not initialized - cannot process with LLM")
            return []

        cache_key = self.cache._generate_cache_key(events_df_chunk, local_day)
        cached_response = self.cache.get_cached_response(cache_key)
        if cached_response is not None:
            return cached_response

        prompt = self._build_prompt(events_df_chunk, local_day)
        if not prompt:
            return []

        try:
            config = genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            )

            # Use 'config' parameter, which is what the installed library version expects.
            # The fallback logic for 'generation_config' has been removed for simplicity and to fix linting errors.
            response = self.client.models.generate_content(
                model=self.settings.ENRICHMENT_MODEL_NAME,
                contents=prompt,
                config=config
            )

            if response.prompt_feedback and response.prompt_feedback.block_reason:
                log.error(f"Prompt blocked by Gemini: {response.prompt_feedback.block_reason}")
                return []

            if not response.text:
                log.warning("Empty response from LLM for chunk")
                return []

            cleaned_text = response.text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:].strip()
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3].strip()

            try:
                timeline_data = json.loads(cleaned_text)
                entries = [TimelineEntry.model_validate(entry) for entry in timeline_data]
                self.cache.save_to_cache(cache_key, entries)
                return entries
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                log.error(f"Failed to parse LLM JSON response for chunk: {e}. Response text: {response.text[:500]}")
                return []

        except Exception as e:
            log.error(f"LLM processing failed for chunk on {local_day}: {e}", exc_info=True)
            return []


class TimelineProcessor:
    """Main timeline processing orchestrator."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.aggregator = EventAggregator(settings)
        self.llm_processor = LLMProcessor(settings)

    def get_local_timezone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.settings.LOCAL_TZ)
        except Exception as e:
            log.warning(f"Failed to get timezone {self.settings.LOCAL_TZ}: {e}, using UTC")
            return ZoneInfo("UTC")

    def get_processing_windows(self, con: duckdb.DuckDBPyConnection) -> List[ProcessingWindow]:
        query = """
            SELECT DISTINCT e.local_day
            FROM events e
            LEFT JOIN event_state es ON e.id = es.event_id
            WHERE es.event_id IS NULL
            ORDER BY e.local_day
        """
        result = con.execute(query).fetchall()
        windows = []
        local_tz = self.get_local_timezone()
        for (local_day,) in result:
            start_local = datetime.combine(local_day, time.min, tzinfo=local_tz)
            end_local = datetime.combine(local_day, time.max, tzinfo=local_tz)
            windows.append(ProcessingWindow(
                start_time=start_local.astimezone(timezone.utc),
                end_time=end_local.astimezone(timezone.utc),
                local_day=local_day
            ))
        return windows

    def fetch_events_for_window(self, con: duckdb.DuckDBPyConnection, window: ProcessingWindow) -> List[Dict[str, Any]]:
        df = con.execute("""
            SELECT e.id, e.start_time, e.end_time, dad.app, dad.title, dad.url
            FROM events e
            LEFT JOIN digital_activity_data dad ON e.id = dad.event_id
            LEFT JOIN event_state es ON e.id = es.event_id
            WHERE es.event_id IS NULL AND e.local_day = ?
            ORDER BY e.start_time
        """, [window.local_day]).pl()
        if 'id' in df.columns:
            df = df.with_columns(pl.col('id').cast(pl.Utf8))
        return df.to_dicts()

    def merge_consecutive_entries(self, entries: List[TimelineEntry]) -> List[TimelineEntry]:
        if not entries: return []
        entries.sort(key=lambda e: e.start)
        merged = [entries[0]]
        for entry in entries[1:]:
            last = merged[-1]
            gap_seconds = (entry.start - last.end).total_seconds()
            activity_match = last.activity.lower().strip() == entry.activity.lower().strip()
            project_match = (last.project or "").lower().strip() == (entry.project or "").lower().strip()
            if activity_match and project_match and -60 <= gap_seconds <= 300:
                last.end = max(last.end, entry.end)
                if entry.notes and entry.notes not in (last.notes or ""):
                    last.notes = ((last.notes or "") + f" | {entry.notes}").strip(" |")
            else:
                merged.append(entry)
        return merged

    def fill_gaps(self, entries: List[TimelineEntry], window: ProcessingWindow) -> List[TimelineEntry]:
        if not entries:
            return [TimelineEntry(start=window.start_time, end=window.end_time, activity=DEFAULT_IDLE_ACTIVITY, project=None, notes="No digital activity recorded for this day.")]
        entries.sort(key=lambda e: e.start)
        filled = []
        if entries[0].start > window.start_time and (entries[0].start - window.start_time).total_seconds() > 300:
            filled.append(TimelineEntry(start=window.start_time, end=entries[0].start, activity=DEFAULT_IDLE_ACTIVITY, notes="Device idle or user away at start of day."))
        filled.append(entries[0])
        for i in range(1, len(entries)):
            prev_end, curr_start = entries[i-1].end, entries[i].start
            if curr_start > prev_end and (curr_start - prev_end).total_seconds() > 300:
                filled.append(TimelineEntry(start=prev_end, end=curr_start, activity=DEFAULT_IDLE_ACTIVITY, notes="Device idle or user away."))
            filled.append(entries[i])
        last_end = filled[-1].end
        if window.end_time > last_end and (window.end_time - last_end).total_seconds() > 300:
            filled.append(TimelineEntry(start=last_end, end=window.end_time, activity=DEFAULT_IDLE_ACTIVITY, notes="Device idle or user away at end of day."))
        return sorted(filled, key=lambda e: e.start)

    def resolve_projects(self, con: duckdb.DuckDBPyConnection, entries: List[TimelineEntry]) -> List[TimelineEntry]:
        try:
            resolver = ProjectResolver(con, self.settings)
            for entry in entries:
                context = f"{entry.activity} | {entry.notes or ''}"
                if not entry.project:
                    resolved_project = resolver.resolve(context)
                    if resolved_project:
                        entry.project = resolved_project
            return entries
        except Exception as e:
            log.warning(f"Project resolution failed: {e}. Continuing without.")
            return entries

    @with_db_write_retry()
    def save_timeline_entries(self, con: duckdb.DuckDBPyConnection, entries: List[TimelineEntry], source_events: List[Dict[str, Any]], local_day: date) -> None:
        is_empty_day = not entries
        con.begin()
        try:
            # 1. Mark all source events for the day as processed using the new event_state table.
            # This is an idempotent insert, so it's safe to run even if some events are already marked.
            if source_events:
                log.debug(f"Marking {len(source_events)} events as processed for {local_day}.")
                event_ids_to_mark = [(e['id'],) for e in source_events]
                con.executemany(
                    "INSERT INTO event_state (event_id) VALUES (?) ON CONFLICT DO NOTHING",
                    event_ids_to_mark,
                )

            # 2. Clear existing timeline data for the day to ensure idempotency.
            log.debug(f"Deleting existing timeline data for {local_day} to ensure idempotency.")
            # Correctly order deletion to respect foreign key constraints.
            # 1. Get IDs of timeline entries to be deleted.
            entry_ids_to_delete = [row[0] for row in con.execute("SELECT id FROM timeline_entries WHERE local_day = ?", [local_day]).fetchall()]

            if entry_ids_to_delete:
                placeholders = ", ".join(["?"] * len(entry_ids_to_delete))
                
                # 2. Delete from timeline_source_events, which references timeline_entries.
                con.execute(f"DELETE FROM timeline_source_events WHERE entry_id IN ({placeholders})", entry_ids_to_delete)
                
                # 3. Now it's safe to delete from timeline_entries.
                con.execute(f"DELETE FROM timeline_entries WHERE id IN ({placeholders})", entry_ids_to_delete)

            # 4. Clean up projects that are no longer referenced by any timeline entries.
            con.execute("""
                DELETE FROM project_aliases pa
                WHERE NOT EXISTS (
                    SELECT 1 FROM timeline_entries te WHERE te.project_id = pa.project_id
                );
            """)
            con.execute("""
                DELETE FROM projects p
                WHERE NOT EXISTS (
                    SELECT 1 FROM timeline_entries te WHERE te.project_id = p.id
                );
            """)

            # 3. Insert new timeline entries and link to source events.
            if not is_empty_day:
                project_map = {row[0].lower(): row[1] for row in con.execute("SELECT name, id FROM projects").fetchall()}
                source_events_df = pl.from_dicts(source_events)
                resolver = ProjectResolver(con, self.settings)

                log.debug(f"Inserting {len(entries)} new timeline entries.")
                for entry in entries:
                    project_id = None
                    if entry.project:
                        project_name_lower = entry.project.lower()
                        if project_name_lower not in project_map:
                            # Project does not exist, create it
                            log.info(f"Creating new project: {entry.project}")
                            context = f"{entry.activity} | {entry.notes or ''}"
                            resolver.learn(entry.project, context)
                            # Refresh project map
                            project_map = {row[0].lower(): row[1] for row in con.execute("SELECT name, id FROM projects").fetchall()}
                        
                        project_id = project_map.get(project_name_lower)

                    entry_id_result = con.execute("INSERT INTO timeline_entries (id, start_time, end_time, title, summary, project_id) VALUES (gen_random_uuid(), ?, ?, ?, ?, ?) RETURNING id", [entry.start, entry.end, entry.activity, entry.notes, project_id]).fetchone()
                    if not entry_id_result: continue
                    entry_id = entry_id_result[0]
                    overlapping_events = source_events_df.filter((pl.col("start_time") < entry.end) & (pl.col("end_time") > entry.start))
                    if not overlapping_events.is_empty():
                        link_params = [(str(entry_id), str(event_id)) for event_id in overlapping_events['id']]
                        con.executemany("INSERT INTO timeline_source_events (entry_id, event_id) VALUES (?, ?)", link_params)

            con.commit()
            if not is_empty_day:
                log.info(f"Successfully saved {len(entries)} timeline entries for {local_day}.")
            else:
                log.info(f"Successfully cleared old data and marked events as processed for empty day: {local_day}.")
        except Exception as e:
            log.error(f"Transaction to save timeline entries failed for {local_day}. Rolling back. Error: {e}", exc_info=True)
            con.rollback()
            raise

    def process_timeline_for_window(self, con: duckdb.DuckDBPyConnection, window: ProcessingWindow) -> None:
        log.info(f"Processing timeline for {window.local_day}")
        
        #+ REVERTED: Check for the client object, not the model object.
        if not self.llm_processor.client:
             log.error(f"LLM client is not initialized. Cannot process window for {window.local_day}.")
             return

        try:
            source_events = self.fetch_events_for_window(con, window)
            if not source_events:
                log.info(f"No pending events for {window.local_day}.")
                return

            all_timeline_entries = []
            total_events = len(source_events)
            num_chunks = (total_events + PROCESSING_CHUNK_SIZE - 1) // PROCESSING_CHUNK_SIZE
            log.info(f"Total events to process: {total_events}. Splitting into {num_chunks} chunk(s).")
            
            for i in range(0, total_events, PROCESSING_CHUNK_SIZE):
                chunk_of_event_dicts = source_events[i : i + PROCESSING_CHUNK_SIZE]
                current_chunk_num = (i // PROCESSING_CHUNK_SIZE) + 1
                log.info(f"--- Processing Chunk {current_chunk_num}/{num_chunks} ({len(chunk_of_event_dicts)} events) ---")
                events_df_chunk = self.aggregator.aggregate_events(chunk_of_event_dicts)
                chunk_entries = self.llm_processor.process_chunk_with_llm(events_df_chunk, window.local_day)
                if chunk_entries:
                    log.info(f"LLM returned {len(chunk_entries)} entries for chunk {current_chunk_num}.")
                    all_timeline_entries.extend(chunk_entries)
                else:
                    log.warning(f"LLM returned no entries for chunk {current_chunk_num}.")

            if all_timeline_entries:
                log.info(f"Aggregating {len(all_timeline_entries)} total entries from all chunks.")
                processed_entries = self.merge_consecutive_entries(all_timeline_entries)
                filled_entries = self.fill_gaps(processed_entries, window)
                final_entries = self.resolve_projects(con, filled_entries)
            else:
                log.warning(f"LLM returned no entries for any chunk. The day will be marked as idle.")
                final_entries = self.fill_gaps([], window)
            
            self.save_timeline_entries(con, final_entries, source_events, window.local_day)
            log.info(f"Successfully processed and saved {len(final_entries)} timeline entries for {window.local_day}")

        except Exception as e:
            log.error(f"A critical error occurred in process_timeline_for_window: {e}", exc_info=True)
            raise

# Public API functions
def process_pending_events(con: duckdb.DuckDBPyConnection, settings: Settings) -> None:
    log.info("Starting timeline processing for pending events")
    processor = TimelineProcessor(settings)
    windows = processor.get_processing_windows(con)
    if not windows:
        log.info("No pending events to process")
        return
    log.info(f"Found {len(windows)} day(s) with pending events to process.")
    for window in windows:
        try:
            processor.process_timeline_for_window(con, window)
        except Exception as e:
            log.error(f"Failed to process window for {window.local_day}. Moving to next window. Error: {e}")
            continue
    log.info("Timeline processing completed")

def process_pending_events_sync(con: duckdb.DuckDBPyConnection, settings: Settings) -> None:
    process_pending_events(con, settings)
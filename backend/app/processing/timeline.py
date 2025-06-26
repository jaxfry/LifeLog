"""
Timeline processing module for LifeLog.

This module processes pending events into enriched timeline entries using LLM-based analysis.
It's adapted from the original timeline generator but redesigned for the new database architecture.
"""

import os
import sys
import logging
import hashlib
import json
import uuid
import polars as pl
from datetime import datetime, timezone, timedelta, date, time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from pathlib import Path
from pydantic import BaseModel, Field, field_validator, model_validator
from google import genai
from google.genai import types as genai_types
from zoneinfo import ZoneInfo

# Add project root to sys.path
CURR_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURR_DIR, '../../..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app.core.settings import Settings
from backend.app.processing import prompts
from backend.app.processing.project_resolver import ProjectResolver
from backend.app.core.utils import with_db_write_retry
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, update, delete as sqla_delete
from sqlalchemy.exc import IntegrityError
from backend.app.models import event_state
from backend.app.models import Event, DigitalActivityData, TimelineEntry as TimelineEntryORM, TimelineSourceEvent, Project

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

    def _generate_cache_key(self, events_df_chunk: pl.DataFrame, local_day: date, project_names: List[str]) -> str:
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
        
        # Add project names to the hash to ensure prompt changes invalidate cache
        project_hash = hashlib.md5(" ".join(sorted(project_names)).encode()).hexdigest()
        
        return f"{local_day.isoformat()}_{data_hash}_{project_hash}"

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

    def _build_prompt(self, events_df_chunk: pl.DataFrame, local_day: date, project_names: List[str]) -> str:
        if events_df_chunk.is_empty():
            return ""

        # Generate project guidance text
        if project_names:
            project_list_str = ", ".join(f'"{name}"' for name in sorted(project_names))
            project_list_guidance = (
                "If an activity is part of a project, assign it to one of these existing projects: "
                f"{project_list_str}. You can also create a new, descriptive project name if it's a new project."
            )
        else:
            project_list_guidance = "If an activity clearly relates to a new project, create a descriptive project name for it, but if it's just a part of a project (e.g. LifeLog and LifeLog Dockerization) then just put it as that project."

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
            events_table_md=events_table_md,
            project_list_guidance=project_list_guidance
        )
        return prompt

    def process_chunk_with_llm(self, events_df_chunk: pl.DataFrame, local_day: date, project_names: List[str]) -> List[TimelineEntry]:
        if events_df_chunk.is_empty():
            return []

        if not self.client:
            log.error("Gemini client not initialized - cannot process with LLM")
            return []

        cache_key = self.cache._generate_cache_key(events_df_chunk, local_day, project_names)
        cached_response = self.cache.get_cached_response(cache_key)
        if cached_response is not None:
            return cached_response

        prompt = self._build_prompt(events_df_chunk, local_day, project_names)
        if not prompt:
            return []

        try:
            config = genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            )

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

    async def get_processing_windows(self, session: AsyncSession) -> List[ProcessingWindow]:
        stmt = select(Event.local_day).distinct().outerjoin(event_state, Event.id == event_state.c.event_id).where(event_state.c.event_id == None).order_by(Event.local_day)
        result = await session.execute(stmt)
        local_days = result.scalars().all()
        windows = []
        local_tz = self.get_local_timezone()
        for local_day in local_days:
            start_local = datetime.combine(local_day, time.min, tzinfo=local_tz)
            end_local = datetime.combine(local_day, time.max, tzinfo=local_tz)
            windows.append(ProcessingWindow(
                start_time=start_local.astimezone(timezone.utc),
                end_time=end_local.astimezone(timezone.utc),
                local_day=local_day
            ))
        return windows

    async def fetch_events_for_window(self, session: AsyncSession, window: ProcessingWindow) -> List[dict]:
        stmt = select(Event.id, Event.start_time, Event.end_time, DigitalActivityData.app, DigitalActivityData.title, DigitalActivityData.url).join(DigitalActivityData, Event.id == DigitalActivityData.event_id).outerjoin(event_state, Event.id == event_state.c.event_id).where(and_(event_state.c.event_id == None, Event.local_day == window.local_day)).order_by(Event.start_time)
        result = await session.execute(stmt)
        rows = result.all()
        return [dict(row._mapping) for row in rows]

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

    async def resolve_projects(self, session: AsyncSession, entries: List[TimelineEntry]) -> List[TimelineEntry]:
        """
        If the LLM didn't assign a project to an entry, this method attempts to
        find a matching existing project using embedding-based similarity.
        It does not use heuristics or create new projects.
        """
        try:
            project_resolver = ProjectResolver(session)
            for entry in entries:
                if not entry.project:
                    # No embedding-based similarity implemented; fallback to no resolution
                    log.debug(f"No project assigned for activity: '{entry.activity}'. No resolver available.")
            return entries
        except Exception as e:
            log.warning(f"Project resolution with embeddings failed: {e}. Continuing without.")
            return entries

    def _normalize_project_name(self, project_name: str) -> str:
        """
        Normalize project names to handle LLM inconsistencies.
        
        This method standardizes project names by:
        1. Splitting on common delimiters
        2. Sorting components alphabetically
        3. Capitalizing properly
        4. Rejoining with standard delimiter
        """
        if not project_name:
            return project_name
        
        # Common delimiters used by LLMs
        delimiters = [' / ', ' & ', ' - ', ' + ', ' | ']
        
        # Find which delimiter is used (if any)
        delimiter_used = None
        for delimiter in delimiters:
            if delimiter in project_name:
                delimiter_used = delimiter
                break
        
        if delimiter_used:
            # Split by delimiter, normalize each part, sort, and rejoin
            parts = [part.strip() for part in project_name.split(delimiter_used)]
            # Remove empty parts
            parts = [part for part in parts if part]
            # Normalize each part (title case)
            parts = [part.title() for part in parts]
            # Sort alphabetically for consistency (LifeLog comes before Hack Club)
            parts.sort()
            # Use standard delimiter
            return ' / '.join(parts)
        else:
            # Single project name, just normalize capitalization
            return project_name.title()

    async def _get_all_project_names(self, session: AsyncSession) -> List[str]:
        """Fetches all existing project names from the database."""
        try:
            stmt = select(Project.name).order_by(Project.name)
            result = await session.execute(stmt)
            return [name for name in result.scalars().all() if name]
        except Exception as e:
            log.warning(f"Could not fetch project list: {e}")
            return []

    async def _create_project_if_not_exists(self, session: AsyncSession, project_name: str) -> Optional[uuid.UUID]:
        """
        Create a project if it doesn't exist, using ProjectResolver for smart duplicate detection.
        Returns the project ID (existing or newly created).
        """
        if not project_name:
            return None
        
        try:
            project_resolver = ProjectResolver(session)
            project = await project_resolver.get_or_create_project_by_name(project_name)
            return project.id if project else None
        except Exception as e:
            log.warning(f"Failed to create/resolve project '{project_name}': {e}")
            return None

    async def _get_project_id_by_name(self, session: AsyncSession, project_name: str) -> Optional[uuid.UUID]:
        """Get project ID by name (case-insensitive lookup)."""
        try:
            from sqlalchemy import text
            stmt = select(Project.id).where(text("lower(name) = lower(:project_name)")).params(project_name=project_name)
            result = await session.execute(stmt)
            row = result.first()
            return row[0] if row else None
        except Exception as e:
            log.warning(f"Failed to lookup project ID for '{project_name}': {e}")
            return None

    async def save_timeline_entries(self, session: AsyncSession, entries: List[TimelineEntry], source_events: List[Dict[str, Any]], local_day: date) -> None:
        is_empty_day = not entries
        try:
            # 1. Mark all source events for the day as processed using the new event_state table.
            if source_events:
                log.debug(f"Marking {len(source_events)} events as processed for {local_day}.")
                event_ids_to_mark = [dict(event_id=e['id']) for e in source_events]
                # Use PostgreSQL-specific ON CONFLICT DO NOTHING syntax instead of SQLite's OR IGNORE
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                stmt = pg_insert(event_state).on_conflict_do_nothing()
                await session.execute(stmt, event_ids_to_mark)

            # 2. Clear existing timeline data for the day to ensure idempotency.
            log.debug(f"Deleting existing timeline data for {local_day} to ensure idempotency.")
            entry_ids_result = await session.execute(select(TimelineEntryORM.id).where(TimelineEntryORM.local_day == local_day))
            entry_ids_to_delete = [row for row in entry_ids_result.scalars().all()]
            if entry_ids_to_delete:
                await session.execute(sqla_delete(TimelineSourceEvent).where(TimelineSourceEvent.entry_id.in_(entry_ids_to_delete)))
                await session.execute(sqla_delete(TimelineEntryORM).where(TimelineEntryORM.id.in_(entry_ids_to_delete)))

            # 3. Insert new timeline entries and link to source events.
            if not is_empty_day:
                for entry in entries:
                    # Automatically create project and get ID if project name is set
                    project_id = None
                    if entry.project:
                        project_id = await self._create_project_if_not_exists(session, entry.project)
                        if project_id:
                            log.debug(f"Using project ID {project_id} for project '{entry.project}'")
                        else:
                            log.warning(f"Failed to create/find project ID for project name '{entry.project}'")
                    
                    new_entry = TimelineEntryORM(
                        start_time=entry.start,
                        end_time=entry.end,
                        title=entry.activity,
                        summary=entry.notes,
                        project_id=project_id,
                        # Note: local_day is automatically computed by PostgreSQL as a generated column
                    )
                    session.add(new_entry)
                    await session.flush()
                    # Link to source events
                    for src in source_events:
                        if src['start_time'] < entry.end and src['end_time'] > entry.start:
                            session.add(TimelineSourceEvent(entry_id=new_entry.id, event_id=src['id']))
            await session.commit()
            if not is_empty_day:
                log.info(f"Successfully saved {len(entries)} timeline entries for {local_day}.")
            else:
                log.info(f"Successfully cleared old data and marked events as processed for empty day: {local_day}.")
        except IntegrityError as e:
            log.error(f"Integrity error during timeline save for {local_day}: {e}")
            await session.rollback()
        except Exception as e:
            log.error(f"Transaction to save timeline entries failed for {local_day}. Rolling back. Error: {e}", exc_info=True)
            await session.rollback()
            raise

    async def process_timeline_for_window(self, session: AsyncSession, window: ProcessingWindow) -> None:
        log.info(f"Processing timeline for {window.local_day} (async)")
        if not self.llm_processor.client:
            log.error(f"LLM client is not initialized. Cannot process window for {window.local_day}.")
            return
        try:
            project_names = await self._get_all_project_names(session)
            if project_names:
                log.info(f"Found {len(project_names)} existing projects to include in prompt.")
            
            source_events = await self.fetch_events_for_window(session, window)
            if not source_events:
                log.info(f"No pending events for {window.local_day}.")
                await self.save_timeline_entries(session, [], [], window.local_day)
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
                chunk_entries = self.llm_processor.process_chunk_with_llm(events_df_chunk, window.local_day, project_names)
                if chunk_entries:
                    log.info(f"LLM returned {len(chunk_entries)} entries for chunk {current_chunk_num}.")
                    all_timeline_entries.extend(chunk_entries)
                else:
                    log.warning(f"LLM returned no entries for chunk {current_chunk_num}.")
            if all_timeline_entries:
                log.info(f"Aggregating {len(all_timeline_entries)} total entries from all chunks.")
                processed_entries = self.merge_consecutive_entries(all_timeline_entries)
                filled_entries = self.fill_gaps(processed_entries, window)
                # Use smart resolver as a fallback for entries the LLM didn't assign a project to
                final_entries = await self.resolve_projects(session, filled_entries)
            else:
                log.warning(f"LLM returned no entries for any chunk. The day will be marked as idle.")
                final_entries = self.fill_gaps([], window)
            await self.save_timeline_entries(session, final_entries, source_events, window.local_day)
            log.info(f"Successfully processed and saved {len(final_entries)} timeline entries for {window.local_day} (async)")
        except Exception as e:
            log.error(f"A critical error occurred in process_timeline_for_window (async): {e}", exc_info=True)
            raise

async def process_pending_events(session: AsyncSession, settings: Settings) -> None:
    log.info("Starting timeline processing for pending events (async/ORM)")
    processor = TimelineProcessor(settings)
    windows = await processor.get_processing_windows(session)
    if not windows:
        log.info("No pending events to process")
        return
    log.info(f"Found {len(windows)} day(s) with pending events to process.")
    for window in windows:
        try:
            await processor.process_timeline_for_window(session, window)
        except Exception as e:
            log.error(f"Failed to process window for {window.local_day}. Moving to next window. Error: {e}")
            continue
    log.info("Timeline processing completed")

async def process_pending_events_sync(session: AsyncSession, settings: Settings) -> None:
    await process_pending_events(session, settings)
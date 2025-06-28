# central_server/processing_service/logic/timeline.py
"""
Timeline processing module for LifeLog Data Processing Service.
Adapted from the original backend.app.processing.timeline.
This version does not interact directly with a database for fetching events
or saving timeline entries. It processes data passed to it and returns
the results.
"""

from datetime import datetime, timezone, timedelta, date, time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo
import logging
import json  # FIX: Add missing import
import hashlib  # FIX: Add missing import
import polars as pl  # FIX: Add missing import
import asyncio

# Google GenAI
from google import genai
from google.genai import types as genai_types

# Local imports for this service
from central_server.processing_service.logic.settings import settings as service_settings, Settings as ServiceSettingsType
from central_server.processing_service.logic import prompts
from central_server.processing_service.logic.project_resolver import ProjectResolver
from central_server.processing_service.models import TimelineEntry, ProcessingEventData # Use absolute import

log = logging.getLogger(__name__)

# Constants
TIMELINE_SOURCE = "timeline_processor_service" # Modified source name
DEFAULT_IDLE_ACTIVITY = "Idle / Away"
PROCESSING_CHUNK_SIZE = 500

@dataclass
class ProcessingWindowStub:
    """
    Represents a time window for processing events, simplified for this service.
    The worker will determine the local_day and overall start/end for a batch.
    """
    start_time: datetime # Overall start for the batch of events
    end_time: datetime   # Overall end for the batch of events
    local_day: date      # The local day these events belong to

class LLMResponseCache:
    """Manages caching of LLM responses."""

    def __init__(self, settings: ServiceSettingsType):
        self.settings = settings
        self.cache_enabled = settings.ENABLE_LLM_CACHE
        self.cache_dir = settings.CACHE_DIR # Uses new settings

        if self.cache_enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            log.info(f"LLM cache enabled, using directory: {self.cache_dir}")
        else:
            log.info("LLM cache disabled")

    def _generate_cache_key(self, events_df_chunk: pl.DataFrame, local_day: date, project_names: List[str]) -> str:
        if events_df_chunk.is_empty():
            return f"empty_{local_day.isoformat()}_ps" # Added _ps for processing service
        
        # Select specific columns that influence the LLM prompt
        # Ensure consistent order and content for hashing
        # Fill nulls to avoid issues with different representations of missing data
        cols_for_hash = ["time_display", "duration_s", "app", "title", "url"]
        
        # Ensure all columns exist, filling with empty string if not (should not happen with ProcessingEventData)
        present_cols = [col for col in cols_for_hash if col in events_df_chunk.columns]
        
        if not present_cols: # Should not happen if events_df_chunk is not empty
             data_str = ""
        else:
            data_str = (
                events_df_chunk
                .select(present_cols)
                .fill_null("") # Fill nulls before converting to string
                .sort(by=present_cols[0] if present_cols else "time_display", descending=False) # Consistent sort
                .to_pandas()
                .to_string()
            )
        data_hash = hashlib.md5(data_str.encode()).hexdigest()
        project_hash = hashlib.md5(" ".join(sorted(project_names)).encode()).hexdigest()
        return f"{local_day.isoformat()}_{data_hash}_{project_hash}_ps"

    def get_cached_response(self, cache_key: str) -> Optional[List[TimelineEntry]]:
        if not self.cache_enabled:
            return None
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None
        try:
            cache_age = datetime.now(timezone.utc) - datetime.fromtimestamp(cache_file.stat().st_mtime, tz=timezone.utc)
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
                try:
                    cache_file.unlink()
                except OSError as unlink_e:
                    log.error(f"Failed to unlink corrupted cache file {cache_file}: {unlink_e}")
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

    def __init__(self, settings: ServiceSettingsType):
        self.settings = settings

    def aggregate_events_from_data(self, events_data: List[ProcessingEventData]) -> pl.DataFrame:
        """
        Aggregates ProcessingEventData objects into a Polars DataFrame for the LLM.
        """
        if not events_data:
            return pl.DataFrame()

        # Convert Pydantic models to list of dicts for Polars
        dict_events = [event.model_dump() for event in events_data]
        
        df = pl.from_dicts(dict_events)

        # Ensure required columns are present from ProcessingEventData
        if "start_time" not in df.columns or "end_time" not in df.columns:
            log.error("DataFrame from ProcessingEventData is missing 'start_time' or 'end_time'.")
            return pl.DataFrame()
        
        # Duration is already calculated in ProcessingEventData, ensure it's used or recalculated if needed
        # df = df.with_columns(((pl.col("end_time") - pl.col("start_time")).dt.total_seconds()).alias("duration_s"))
        # Using pre-calculated duration_s from ProcessingEventData

        df_activities = df.filter(pl.col("app") != self.settings.AFK_APP_NAME) # Filter out AFK
        
        if df_activities.is_empty():
            log.info("No non-AFK activities in this batch of ProcessingEventData.")
            return pl.DataFrame()

        if self.settings.ENRICHMENT_MIN_DURATION_S > 0:
            df_activities = df_activities.filter(pl.col("duration_s") >= self.settings.ENRICHMENT_MIN_DURATION_S)
        
        if df_activities.is_empty():
            log.info("No activities remaining after duration filter from ProcessingEventData.")
            return pl.DataFrame()

        truncate_limit = self.settings.ENRICHMENT_PROMPT_TRUNCATE_LIMIT
        ellipsis_suffix = "…"
        
        # Prepare for prompt: ensure start_time is datetime for strftime
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
        log.info(f"Prepared {df_for_prompt.height} activity events for LLM prompt from ProcessingEventData.")
        return df_for_prompt

class LLMProcessor:
    """Handles LLM-based timeline enrichment."""

    def __init__(self, settings: ServiceSettingsType):
        self.settings = settings
        self.client = None
        self.cache = LLMResponseCache(settings)
        # Don't initialize client immediately - do it lazily when needed
        self._client_initialized = False

    def _initialize_client(self):
        """Lazy initialization of the LLM client."""
        if self._client_initialized:
            return
            
        try:
            api_key = self.settings.GEMINI_API_KEY # Use from new settings
            if not api_key or api_key == "YOUR_API_KEY_HERE": # Check placeholder
                raise ValueError("GEMINI_API_KEY not configured in service settings")
            
            self.client = genai.Client(api_key=api_key)
            self._client_initialized = True
            log.info(f"Gemini client initialized successfully with model target: {self.settings.ENRICHMENT_MODEL_NAME}")
            
        except Exception as e:
            log.error(f"Failed to initialize Gemini client: {e}. LLM processing will be disabled.", exc_info=True)
            self.client = None
            self._client_initialized = True  # Mark as attempted to avoid repeated failures

    def _build_prompt(self, events_df_chunk: pl.DataFrame, local_day: date, project_names: List[str]) -> str:
        if events_df_chunk.is_empty():
            return ""

        project_list_guidance = "If an activity clearly relates to a new project, create a descriptive project name for it."
        if project_names: # Use known_project_names passed in
            project_list_str = ", ".join(f'"{name}"' for name in sorted(project_names))
            project_list_guidance = (
                "If an activity is part of a project, assign it to one of these existing projects: "
                f"{project_list_str}. You can also create a new, descriptive project name if it's a new project."
            )
        
        required_cols = ["time_display", "duration_s", "app", "title", "url"]
        # This part should be less necessary if aggregate_events_from_data correctly prepares df
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
        # Use prompts from local .prompts module
        prompt = prompts.TIMELINE_ENRICHMENT_SYSTEM_PROMPT.format(
            day_iso=local_day.isoformat(),
            schema_description=schema_description,
            events_table_md=events_table_md,
            project_list_guidance=project_list_guidance
        )
        return prompt

    async def process_chunk_with_llm(self, events_df_chunk: pl.DataFrame, local_day: date, project_names: List[str]) -> List[TimelineEntry]:
        if events_df_chunk.is_empty():
            log.warning("Empty event chunk provided to LLM processor.")
            return []

        # Initialize client only when actually needed
        if not self._client_initialized:
            log.info("Initializing LLM client on first use...")
            self._initialize_client()

        if not self.client:
            log.error("LLM client not available. Cannot process chunk.")
            return []

        cache_key = self.cache._generate_cache_key(events_df_chunk, local_day, project_names)
        cached_response = self.cache.get_cached_response(cache_key)
        if cached_response is not None:
            return cached_response

        prompt_text = self._build_prompt(events_df_chunk, local_day, project_names)
        if not prompt_text:
            return []
        
        try:
            config = genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            )
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.settings.ENRICHMENT_MODEL_NAME,
                contents=prompt_text,
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

class TimelineProcessorService:
    """Orchestrates timeline processing within the service."""

    def __init__(self, settings: ServiceSettingsType):
        self.settings = settings
        self.aggregator = EventAggregator(settings)
        self.llm_processor = LLMProcessor(settings)
        # Remove project_resolver from here; project resolution is a fallback only

    def get_local_timezone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.settings.LOCAL_TZ)
        except Exception as e:
            log.warning(f"Failed to get timezone {self.settings.LOCAL_TZ}: {e}, using UTC")
            return ZoneInfo("UTC")

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

    def fill_gaps(self, entries: List[TimelineEntry], processing_window: ProcessingWindowStub) -> List[TimelineEntry]:
        if not entries:
            # If no entries at all for the window, create a single idle block for the whole duration
            return [TimelineEntry(
                start=processing_window.start_time, 
                end=processing_window.end_time, 
                activity=DEFAULT_IDLE_ACTIVITY, 
                project=None, 
                notes="No digital activity recorded for this period."
            )]

        entries.sort(key=lambda e: e.start)
        filled: List[TimelineEntry] = []
        
        # Use the configurable minimum gap duration from settings
        min_gap_seconds = self.settings.MIN_GAP_FILL_DURATION_S

        if entries[0].start > processing_window.start_time and \
           (entries[0].start - processing_window.start_time).total_seconds() >= min_gap_seconds:
            filled.append(TimelineEntry(
                start=processing_window.start_time, 
                end=entries[0].start, 
                activity=DEFAULT_IDLE_ACTIVITY, 
                notes="Device idle or user away at start of period."
            ))
        
        filled.append(entries[0])

        for i in range(1, len(entries)):
            prev_end = entries[i-1].end
            curr_start = entries[i].start
            if curr_start > prev_end and (curr_start - prev_end).total_seconds() >= min_gap_seconds:
                filled.append(TimelineEntry(
                    start=prev_end, 
                    end=curr_start, 
                    activity=DEFAULT_IDLE_ACTIVITY, 
                    notes="Device idle or user away."
                ))
            filled.append(entries[i])
        
        # Gap at the end
        last_entry_end = filled[-1].end
        if processing_window.end_time > last_entry_end and \
           (processing_window.end_time - last_entry_end).total_seconds() >= min_gap_seconds:
            filled.append(TimelineEntry(
                start=last_entry_end, 
                end=processing_window.end_time, 
                activity=DEFAULT_IDLE_ACTIVITY, 
                notes="Device idle or user away at end of period."
            ))
            
        return sorted(filled, key=lambda e: e.start) # Ensure sorted

    async def process_events_batch(
        self,
        source_events_data: List[ProcessingEventData],
        batch_local_day: date,
        known_project_names: Optional[List[str]] = None
    ) -> List[TimelineEntry]:
        log.info(f"Processing timeline for {batch_local_day} with {len(source_events_data)} events.")
        if not source_events_data:
            log.info(f"No events in the batch for {batch_local_day}. Returning empty list.")
            return []
        local_tz = self.get_local_timezone()
        day_start_utc = datetime.combine(batch_local_day, time.min, tzinfo=local_tz).astimezone(timezone.utc)
        day_end_utc = datetime.combine(batch_local_day, time.max, tzinfo=local_tz).astimezone(timezone.utc)
        current_processing_window = ProcessingWindowStub(
            start_time=day_start_utc,
            end_time=day_end_utc,
            local_day=batch_local_day
        )
        if len(source_events_data) < self.settings.MIN_EVENTS_FOR_LLM_PROCESSING:
            log.info(f"Only {len(source_events_data)} events (< {self.settings.MIN_EVENTS_FOR_LLM_PROCESSING} threshold). Creating a single idle entry for the day.")
            return [TimelineEntry(
                start=day_start_utc,
                end=day_end_utc,
                activity=DEFAULT_IDLE_ACTIVITY,
                project=None,
                notes=f"Limited activity recorded ({len(source_events_data)} events). Day processed without full analysis."
            )]
        events_df = self.aggregator.aggregate_events_from_data(source_events_data)
        
        all_entries = []
        if not events_df.is_empty():
            if events_df.height > PROCESSING_CHUNK_SIZE:
                log.info(f"Large day detected ({events_df.height} events), processing in chunks of {PROCESSING_CHUNK_SIZE}.")
                
                tasks = []
                for i in range(0, events_df.height, PROCESSING_CHUNK_SIZE):
                    chunk_df = events_df.slice(i, PROCESSING_CHUNK_SIZE)
                    tasks.append(
                        self.llm_processor.process_chunk_with_llm(chunk_df, batch_local_day, known_project_names or [])
                    )
                
                chunk_results = await asyncio.gather(*tasks)
                for entry_list in chunk_results:
                    all_entries.extend(entry_list)
            else:
                log.info(f"Processing {events_df.height} events in a single call.")
                all_entries = await self.llm_processor.process_chunk_with_llm(events_df, batch_local_day, known_project_names or [])
        
        if all_entries:
            log.info(f"LLM returned a total of {len(all_entries)} entries for the day.")
            processed_entries = self.merge_consecutive_entries(all_entries)
            filled_entries = self.fill_gaps(processed_entries, current_processing_window)
            final_entries = filled_entries
        else:
            log.warning(f"LLM returned no entries. The day will be marked as idle.")
            final_entries = self.fill_gaps([], current_processing_window)
        log.info(f"Successfully processed batch, resulting in {len(final_entries)} timeline entries for {batch_local_day}.")
        return final_entries

# IMPORTANT: When saving timeline entries to the database, always use ProjectResolver to resolve or create projects.
# Example usage:
# from central_server.processing_service.logic.project_resolver import ProjectResolver
# ...
# async def save_timeline_entries(session: AsyncSession, entries: List[TimelineEntry]):
#     project_resolver = ProjectResolver(session)
#     for entry in entries:
#         if entry.project:
#             project_obj = await project_resolver.get_or_create_project_by_name(entry.project)
#             # Use project_obj.id when saving the timeline entry
#


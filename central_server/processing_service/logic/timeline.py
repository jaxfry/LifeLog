# central_server/processing_service/logic/timeline.py
"""
Timeline processing module for LifeLog Data Processing Service.
Adapted from the original backend.app.processing.timeline.
This version does not interact directly with a database for fetching events
or saving timeline entries. It processes data passed to it and returns
the results.
"""

from datetime import datetime, timezone, timedelta, date, time
from typing import List, Optional
from dataclasses import dataclass
from zoneinfo import ZoneInfo
import logging
import asyncio

# Local imports for this service
from central_server.processing_service.logic.settings import Settings as ServiceSettingsType
from central_server.processing_service.logic.event_aggregation import EventAggregator
from central_server.processing_service.logic.llm_processing import LLMProcessor
from central_server.processing_service.models import TimelineEntry, ProcessingEventData

log = logging.getLogger(__name__)

# Constants
TIMELINE_SOURCE = "timeline_processor_service"
DEFAULT_IDLE_ACTIVITY = "Idle / Away"
PROCESSING_CHUNK_SIZE = 300

@dataclass
class ProcessingWindowStub:
    """
    Represents a time window for processing events, simplified for this service.
    The worker will determine the local_day and overall start/end for a batch.
    """
    start_time: datetime
    end_time: datetime
    local_day: date

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


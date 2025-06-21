"""
Timeline processing module for LifeLog.

This module processes pending events into enriched timeline entries using LLM-based analysis.
It's adapted from the original timeline generator but redesigned for the new database architecture.
"""

import asyncio
import hashlib
import logging
import os
from datetime import datetime, timezone, timedelta, date, time
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from pathlib import Path
import json

import polars as pl
import duckdb
from pydantic import BaseModel, Field, field_validator, model_validator
from google import genai
from google.genai import types as genai_types
from zoneinfo import ZoneInfo

from backend.app.core.settings import Settings
from backend.app.processing.project_resolver import ProjectResolver

log = logging.getLogger(__name__)

# Constants
TIMELINE_SOURCE = "timeline_processor"
PROCESSING_CHUNK_SIZE = 50  # Process events in chunks
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
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        if isinstance(v, datetime):
            return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)
        raise ValueError("Invalid datetime format")

    @model_validator(mode='after')
    def check_start_before_end(self):
        if self.start and self.end and self.start > self.end:
            raise ValueError(f"End time ({self.end}) must be after start time ({self.start}).")
        return self


class EventAggregator:
    """Aggregates and prepares events for LLM processing."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
    
    def aggregate_events(self, events: List[Dict[str, Any]]) -> pl.DataFrame:
        """Aggregates events into time-based chunks for LLM processing."""
        if not events:
            return pl.DataFrame()
        
        df = pl.from_dicts(events)
        
        # Ensure datetime columns are properly typed
        if "start_time" in df.columns and "end_time" in df.columns:
            # Create time buckets for aggregation
            chunk_duration = timedelta(minutes=self.settings.ENRICHMENT_CHUNK_MINUTES)
            
            # Group events by time chunks
            df_chunked = df.with_columns([
                # Create time bucket
                (pl.col("start_time").dt.truncate(f"{self.settings.ENRICHMENT_CHUNK_MINUTES}m")).alias("time_bucket"),
                # Format time for display
                pl.col("start_time").dt.strftime("%H:%M:%S").alias("time_display"),
                # Calculate duration
                ((pl.col("end_time") - pl.col("start_time")).dt.total_seconds()).alias("duration_s")
            ])
            
            return df_chunked.sort("start_time")
        
        return df


class LLMProcessor:
    """Handles LLM-based timeline enrichment."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the Gemini client."""
        try:
            api_key = os.getenv("GEMINI_API_KEY") or self.settings.GEMINI_API_KEY
            if not api_key or api_key == "YOUR_API_KEY_HERE":
                raise ValueError("GEMINI_API_KEY not configured")
            self.client = genai.Client(api_key=api_key)
            log.info("Gemini client initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize Gemini client: {e}")
            self.client = None  # Ensure client is None on failure
    
    def _build_prompt(self, events_df: pl.DataFrame, local_day: date) -> str:
        """Builds the LLM prompt from events DataFrame."""
        if events_df.is_empty():
            return ""
        
        # Limit events to avoid overly long prompts
        max_events = min(100, len(events_df))  # Limit to 100 events max
        
        # Convert to markdown table for the prompt
        events_table = events_df.head(max_events).select([
            "time_display",
            "duration_s", 
            "app",
            "title",
            "url"
        ]).to_pandas().to_markdown(index=False, maxcolwidths=[8, 8, 15, 30, 30])  # Limit column widths
        
        schema_description = (
            '[{"start": "YYYY-MM-DDTHH:MM:SSZ",'
            '"end": "YYYY-MM-DDTHH:MM:SSZ",'
            '"activity": "string",'
            '"project": "string | null",'
            '"notes": "string | null"}]'
        )
        
        prompt = f"""You are a timeline enrichment assistant. Analyze the digital activity data below and create a concise timeline.

**Date**: {local_day.isoformat()}

**Instructions**:
1. Group similar consecutive activities into meaningful blocks (5-30 minutes each)
2. Create max 20 timeline entries for the day
3. Use descriptive but concise activity names
4. Identify projects when obvious from context
5. Fill major gaps (>15 min) with "Idle / Away"

**Output**: JSON array only, no other text:
{schema_description}

**Events** ({max_events} shown):
{events_table}
"""
        return prompt
    
    async def process_with_llm(self, events_df: pl.DataFrame, local_day: date) -> List[TimelineEntry]:
        """Processes events using LLM and returns structured timeline entries."""
        if events_df.is_empty():
            return []
        
        if not self.client:
            log.error("Gemini client not initialized - cannot process with LLM")
            return []
        
        prompt = self._build_prompt(events_df, local_day)
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
            
            # Parse response JSON
            if not response.text:
                log.warning("Empty response from LLM")
                return []
            
            try:
                timeline_data = json.loads(response.text)
                entries = [TimelineEntry.model_validate(entry) for entry in timeline_data]
                log.info(f"LLM generated {len(entries)} timeline entries for {local_day}")
                return entries
            except json.JSONDecodeError as e:
                log.error(f"Failed to parse LLM JSON response for {local_day}: {e}")
                log.error(f"Response snippet: {response.text[:500]}...")
                # Try to extract valid JSON if possible
                try:
                    # Sometimes the response might have extra text, try to find JSON array
                    start_idx = response.text.find('[')
                    end_idx = response.text.rfind(']') + 1
                    if start_idx >= 0 and end_idx > start_idx:
                        json_part = response.text[start_idx:end_idx]
                        timeline_data = json.loads(json_part)
                        entries = [TimelineEntry.model_validate(entry) for entry in timeline_data]
                        log.info(f"Successfully extracted {len(entries)} entries from partial JSON")
                        return entries
                except:
                    pass
                return []
                
        except Exception as e:
            log.error(f"LLM processing failed for {local_day}: {e}")
            return []


class TimelineProcessor:
    """Main timeline processing orchestrator."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.aggregator = EventAggregator(settings)
        self.llm_processor = LLMProcessor(settings)
    
    def get_local_timezone(self) -> ZoneInfo:
        """Get the configured local timezone."""
        try:
            return ZoneInfo(self.settings.LOCAL_TZ)
        except Exception as e:
            log.warning(f"Failed to get timezone {self.settings.LOCAL_TZ}: {e}, using UTC")
            return ZoneInfo("UTC")
    
    def get_processing_windows(self, con: duckdb.DuckDBPyConnection) -> List[ProcessingWindow]:
        """Get time windows that need processing based on pending events."""
        result = con.execute("""
            SELECT DISTINCT local_day 
            FROM events 
            WHERE processing_status = 'pending'
            ORDER BY local_day
        """).fetchall()
        
        windows = []
        local_tz = self.get_local_timezone()
        
        for (local_day,) in result:
            # Convert local day to UTC time window
            start_local = datetime.combine(local_day, time.min, tzinfo=local_tz)
            end_local = datetime.combine(local_day, time.max, tzinfo=local_tz)
            
            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)
            
            windows.append(ProcessingWindow(
                start_time=start_utc,
                end_time=end_utc,
                local_day=local_day
            ))
        
        return windows
    
    def fetch_events_for_window(self, con: duckdb.DuckDBPyConnection, window: ProcessingWindow) -> List[Dict[str, Any]]:
        """Fetch pending events for a processing window."""
        result = con.execute("""
            SELECT 
                e.id,
                e.start_time,
                e.end_time,
                e.payload_hash,
                dad.app,
                dad.title,
                dad.url,
                dad.hostname
            FROM events e
            LEFT JOIN digital_activity_data dad ON e.id = dad.event_id
            WHERE e.processing_status = 'pending'
            AND e.local_day = ?
            ORDER BY e.start_time
        """, [window.local_day]).fetchall()
        
        events = []
        for row in result:
            events.append({
                'id': row[0],
                'start_time': row[1],
                'end_time': row[2],
                'payload_hash': row[3],
                'app': row[4] or '',
                'title': row[5] or '',
                'url': row[6] or '',
                'hostname': row[7] or ''
            })
        
        return events
    
    def merge_consecutive_entries(self, entries: List[TimelineEntry]) -> List[TimelineEntry]:
        """Merge consecutive entries with similar activities and projects."""
        if not entries:
            return []
        
        entries.sort(key=lambda e: e.start)
        merged = []
        
        for entry in entries:
            if not merged:
                merged.append(entry)
                continue
            
            last = merged[-1]
            gap_seconds = (entry.start - last.end).total_seconds()
            
            # Check if entries can be merged
            activity_match = last.activity.lower() == entry.activity.lower()
            project_match = (last.project or "").lower() == (entry.project or "").lower()
            
            if activity_match and project_match and 0 <= gap_seconds <= 300:  # 5 minute gap
                # Merge entries
                last.end = max(last.end, entry.end)
                if entry.notes and entry.notes not in (last.notes or ""):
                    last.notes = (last.notes or "") + f" | {entry.notes}"
            else:
                merged.append(entry)
        
        return merged
    
    def fill_gaps(self, entries: List[TimelineEntry], window: ProcessingWindow) -> List[TimelineEntry]:
        """Fill gaps in timeline with idle periods."""
        if not entries:
            # No entries, entire day is idle
            return [TimelineEntry(
                start=window.start_time,
                end=window.end_time,
                activity=DEFAULT_IDLE_ACTIVITY,
                project=None,
                notes="No digital activity recorded for this day."
            )]
        
        entries.sort(key=lambda e: e.start)
        filled = []
        
        # Fill gap at start of day
        first = entries[0]
        if first.start > window.start_time:
            gap_duration = (first.start - window.start_time).total_seconds()
            if gap_duration > 300:  # Only fill gaps > 5 minutes
                filled.append(TimelineEntry(
                    start=window.start_time,
                    end=first.start,
                    activity=DEFAULT_IDLE_ACTIVITY,
                    project=None,
                    notes="Device idle or user away at start of day."
                ))
        
        # Add first entry
        filled.append(first)
        
        # Fill gaps between entries
        for i in range(1, len(entries)):
            prev = filled[-1]
            curr = entries[i]
            
            gap_duration = (curr.start - prev.end).total_seconds()
            if gap_duration > 300:  # Only fill gaps > 5 minutes
                filled.append(TimelineEntry(
                    start=prev.end,
                    end=curr.start,
                    activity=DEFAULT_IDLE_ACTIVITY,
                    project=None,
                    notes="Device idle or user away."
                ))
            
            filled.append(curr)
        
        # Fill gap at end of day
        last = filled[-1]
        if last.end < window.end_time:
            gap_duration = (window.end_time - last.end).total_seconds()
            if gap_duration > 300:  # Only fill gaps > 5 minutes
                filled.append(TimelineEntry(
                    start=last.end,
                    end=window.end_time,
                    activity=DEFAULT_IDLE_ACTIVITY,
                    project=None,
                    notes="Device idle or user away at end of day."
                ))
        
        return filled
    
    def resolve_projects(self, con: duckdb.DuckDBPyConnection, entries: List[TimelineEntry]) -> List[TimelineEntry]:
        """Resolve project names using the project resolver."""
        try:
            resolver = ProjectResolver(con, self.settings)
            
            for entry in entries:
                if not entry.project:  # Only resolve if no project specified
                    # Create context from activity and notes
                    context_parts = [entry.activity]
                    if entry.notes:
                        context_parts.append(entry.notes)
                    context = " | ".join(context_parts)
                    
                    resolved_project = resolver.resolve(context)
                    if resolved_project:
                        entry.project = resolved_project
                        log.debug(f"Resolved project '{resolved_project}' for activity '{entry.activity}'")
            
            return entries
        except Exception as e:
            log.warning(f"Project resolution failed: {e}. Continuing without project resolution.")
            return entries
    
    def save_timeline_entries(self, con: duckdb.DuckDBPyConnection, entries: List[TimelineEntry], 
                            source_events: List[Dict[str, Any]]) -> None:
        """Save timeline entries to database and link them to overlapping source events."""
        for entry in entries:
            # Insert timeline entry
            result = con.execute("""
                INSERT INTO timeline_entries (id, start_time, end_time, title, summary, project_id)
                VALUES (
                    gen_random_uuid(),
                    ?,
                    ?,
                    ?,
                    ?,
                    (SELECT id FROM projects WHERE lower(name) = lower(?) LIMIT 1)
                )
                RETURNING id
            """, [
                entry.start,
                entry.end,
                entry.activity,
                entry.notes,
                entry.project
            ]).fetchone()
            
            if result:
                entry_id = result[0]
                
                # Link only to overlapping source events
                for event in source_events:
                    event_start = event['start_time']
                    event_end = event['end_time'] or event_start  # Handle null end_time
                    
                    # Check if event overlaps with timeline entry
                    if (event_start < entry.end and event_end > entry.start):
                        con.execute("""
                            INSERT INTO timeline_source_events (entry_id, event_id)
                            VALUES (?, ?)
                            ON CONFLICT DO NOTHING
                        """, [entry_id, event['id']])
    
    def mark_events_processed(self, con: duckdb.DuckDBPyConnection, source_events: List[Dict[str, Any]]) -> None:
        """Mark events as processed - but only if they're not already linked to timeline entries."""
        for event in source_events:
            event_id = event['id']
            # Check if event is already linked to a timeline entry
            result = con.execute("""
                SELECT COUNT(*) FROM timeline_source_events 
                WHERE event_id = ?
            """, [event_id]).fetchone()
            
            if result:
                linked_count = result[0]
                if linked_count == 0:
                    # Only update status if not linked
                    con.execute("""
                        UPDATE events 
                        SET processing_status = 'processed'
                        WHERE id = ?
                    """, [event_id])
                else:
                    log.debug(f"Skipping status update for event {event_id} - already linked to timeline")
    
    async def process_timeline_for_window(self, con: duckdb.DuckDBPyConnection, window: ProcessingWindow) -> None:
        """Process timeline for a single time window."""
        log.info(f"Processing timeline for {window.local_day}")
        
        try:
            # Fetch events
            events = self.fetch_events_for_window(con, window)
            if not events:
                log.info(f"No events to process for {window.local_day}")
                return
            
            # Aggregate events
            events_df = self.aggregator.aggregate_events(events)
            
            # Process with LLM
            timeline_entries = await self.llm_processor.process_with_llm(events_df, window.local_day)
            
            # Post-process entries
            timeline_entries = self.merge_consecutive_entries(timeline_entries)
            timeline_entries = self.fill_gaps(timeline_entries, window)
            timeline_entries = self.resolve_projects(con, timeline_entries)
            
            # Save to database
            self.save_timeline_entries(con, timeline_entries, events)
            self.mark_events_processed(con, events)
            
            log.info(f"Successfully processed {len(timeline_entries)} timeline entries for {window.local_day}")
            
        except Exception as e:
            log.error(f"Failed to process timeline for {window.local_day}: {e}")
            raise


# Public API functions
async def process_pending_events(con: duckdb.DuckDBPyConnection, settings: Settings) -> None:
    """Process all pending events into timeline entries."""
    log.info("Starting timeline processing for pending events")
    
    processor = TimelineProcessor(settings)
    windows = processor.get_processing_windows(con)
    
    if not windows:
        log.info("No pending events to process")
        return
    
    log.info(f"Processing {len(windows)} time windows")
    
    for window in windows:
        await processor.process_timeline_for_window(con, window)
    
    log.info("Timeline processing completed")


def process_pending_events_sync(con: duckdb.DuckDBPyConnection, settings: Settings) -> None:
    """Synchronous wrapper for process_pending_events."""
    asyncio.run(process_pending_events(con, settings))
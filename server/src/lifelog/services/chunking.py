"""
Timeline Chunking Service

Intelligently groups events into chunks with budget enforcement for LLM processing.
Implements smart boundary detection to create natural groupings.
"""

import logging
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from .. import models

logger = logging.getLogger(__name__)


class ChunkBudget:
    """Budget constraints for chunking."""
    
    def __init__(
        self,
        max_characters: int = 4000,
        max_tokens: Optional[int] = None,
        min_chunk_duration_minutes: int = 5,
        max_chunk_duration_hours: int = 4
    ):
        """
        Initialize chunk budget constraints.
        
        Args:
            max_characters: Maximum characters per chunk (default: 4000)
            max_tokens: Maximum tokens per chunk (estimated if None)
            min_chunk_duration_minutes: Minimum time span for a chunk
            max_chunk_duration_hours: Maximum time span for a chunk
        """
        self.max_characters = max_characters
        self.max_tokens = max_tokens or (max_characters // 4)  # Rough estimate: 1 token ≈ 4 chars
        self.min_chunk_duration = timedelta(minutes=min_chunk_duration_minutes)
        self.max_chunk_duration = timedelta(hours=max_chunk_duration_hours)


class EventChunk:
    """A group of events that will be processed together."""
    
    def __init__(self, events: List[models.Event]):
        self.events = events
        self.start_time = min(e.start_time for e in events)
        self.end_time = max(e.end_time or e.start_time for e in events)
        self.character_count = sum(len(e.summary or "") for e in events)
        self.event_ids = [e.id for e in events if e.id is not None]
    
    def duration(self) -> timedelta:
        """Get the time span covered by this chunk."""
        return self.end_time - self.start_time
    
    def to_text(self) -> str:
        """Convert chunk to text representation for LLM input."""
        lines = []
        for event in sorted(self.events, key=lambda e: e.start_time):
            event_text = f"[{event.start_time.isoformat()}] {event.summary or 'No summary'}"
            if event.end_time:
                duration = (event.end_time - event.start_time).total_seconds() / 60
                event_text += f" (duration: {duration:.1f} min)"
            lines.append(event_text)
        return "\n".join(lines)


class TimelineChunkingService:
    """Service for intelligently chunking events with budget enforcement."""
    
    @staticmethod
    async def chunk_events_for_period(
        session: AsyncSession,
        start_time: datetime,
        end_time: datetime,
        budget: Optional[ChunkBudget] = None
    ) -> List[EventChunk]:
        """
        Chunk events within a time period with intelligent boundary detection.
        
        This method:
        1. Fetches non-superseded events in the period
        2. Groups them into chunks respecting budget limits
        3. Uses intelligent boundary detection for natural breaks
        
        Args:
            session: Database session
            start_time: Start of period to chunk
            end_time: End of period to chunk
            budget: Budget constraints (uses defaults if None)
        
        Returns:
            List of EventChunk objects
        """
        if budget is None:
            budget = ChunkBudget()
        
        # Fetch events in the period (non-superseded only)
        stmt = (
            select(models.Event)
            .where(models.Event.start_time >= start_time)
            .where(models.Event.start_time < end_time)
            .where(models.Event.superseded_by_event_id.is_(None))  # type: ignore[attr-defined]
            .order_by(models.Event.start_time)  # type: ignore[arg-type]
        )
        result = await session.exec(stmt)
        events = list(result.all())
        
        if not events:
            logger.info(f"No events found for period {start_time} to {end_time}")
            return []
        
        logger.info(f"Chunking {len(events)} events for period {start_time} to {end_time}")
        
        # Create chunks with intelligent boundaries
        chunks = []
        current_chunk: List[models.Event] = []
        current_char_count = 0
        
        for i, event in enumerate(events):
            event_chars = len(event.summary or "")
            
            # Check if adding this event would exceed budget
            would_exceed_chars = (current_char_count + event_chars) > budget.max_characters
            
            # Check if chunk has minimum duration (unless it's the last event)
            has_min_duration = False
            if current_chunk:
                chunk_duration = (event.start_time - current_chunk[0].start_time)
                has_min_duration = chunk_duration >= budget.min_chunk_duration
            
            # Detect natural boundaries (activity changes, long gaps)
            is_natural_boundary = TimelineChunkingService._is_natural_boundary(
                current_chunk[-1] if current_chunk else None,
                event,
                events[i + 1] if i + 1 < len(events) else None
            )
            
            # Decision: start new chunk?
            should_break = False
            if current_chunk:
                # Must break if we'd exceed character budget
                if would_exceed_chars:
                    should_break = True
                # Break at natural boundaries if we have minimum duration
                elif is_natural_boundary and has_min_duration:
                    should_break = True
                # Force break if chunk duration is too long
                elif (event.start_time - current_chunk[0].start_time) > budget.max_chunk_duration:
                    should_break = True
            
            if should_break:
                # Finalize current chunk
                if current_chunk:
                    chunks.append(EventChunk(current_chunk))
                # Start new chunk
                current_chunk = [event]
                current_char_count = event_chars
            else:
                # Add to current chunk
                current_chunk.append(event)
                current_char_count += event_chars
        
        # Add final chunk
        if current_chunk:
            chunks.append(EventChunk(current_chunk))
        
        logger.info(f"Created {len(chunks)} chunks from {len(events)} events")
        
        # Validate chunks don't exceed hard limits
        for chunk in chunks:
            if chunk.character_count > budget.max_characters:
                logger.warning(
                    f"Chunk exceeds character budget: {chunk.character_count} > {budget.max_characters}. "
                    f"Consider tighter chunking or event summarization."
                )
        
        return chunks
    
    @staticmethod
    def _is_natural_boundary(
        prev_event: Optional[models.Event],
        current_event: models.Event,
        next_event: Optional[models.Event]
    ) -> bool:
        """
        Detect natural boundaries between events for intelligent chunking.
        
        Natural boundaries include:
        - Long time gaps (>30 min)
        - Changes in activity type (different event types)
        - End of work period / start of break
        
        Args:
            prev_event: Previous event (or None if first)
            current_event: Current event being evaluated
            next_event: Next event (or None if last)
        
        Returns:
            True if this is a natural boundary point
        """
        if not prev_event:
            return False
        
        # Check for time gap
        gap = (current_event.start_time - (prev_event.end_time or prev_event.start_time))
        if gap > timedelta(minutes=30):
            return True
        
        # Check for event type change (indicates activity switch)
        if prev_event.event_type_id != current_event.event_type_id:
            return True
        
        # Check for summary pattern changes (basic heuristic)
        if prev_event.summary and current_event.summary:
            prev_words = set(prev_event.summary.lower().split()[:3])
            curr_words = set(current_event.summary.lower().split()[:3])
            # If first few words are completely different, likely a context switch
            if not prev_words.intersection(curr_words):
                return True
        
        return False
    
    @staticmethod
    def estimate_token_count(text: str) -> int:
        """
        Estimate token count for text.
        
        This is a simple heuristic. For production, consider using tiktoken
        or the actual tokenizer for your LLM.
        
        Args:
            text: Text to estimate tokens for
        
        Returns:
            Estimated token count
        """
        # Simple heuristic: ~4 characters per token on average
        # This varies by language and tokenizer, but is reasonable for English
        return len(text) // 4

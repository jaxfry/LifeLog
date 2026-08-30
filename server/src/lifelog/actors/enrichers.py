"""
Timeline enricher actor for generating timeline blocks from events.

This is a BATCH_WORKER actor that processes events in time periods and generates
enriched timeline blocks using LLM.
"""

import logging
from typing import Any, Optional
from datetime import datetime, timedelta, timezone
from sqlmodel import select

from lifelog.core.actors import ActorBase, ActorConfig, actor_registry
from lifelog import models
from lifelog.db import async_session
from lifelog.services.chunking import TimelineChunkingService, ChunkBudget
from lifelog.services.timeline_generation import TimelineGenerationService

logger = logging.getLogger(__name__)


@actor_registry.register(
    ActorConfig(
        slug="timeline-enricher",
        actor_type=models.ActorType.ENRICHER,
        version="1.0.0",
    )
)
class TimelineEnricher(ActorBase):
    """
    Enricher actor that generates timeline blocks from events.
    
    This actor:
    1. Chunks events for a time period using intelligent boundary detection
    2. Generates timeline blocks via LLM for each chunk
    3. Handles supersedence when regenerating blocks
    """

    async def run(self, data: Any) -> Any:
        """
        Generate timeline blocks for a given time period.
        
        Args:
            data: Dict with keys:
                - start_time: datetime or ISO string
                - end_time: datetime or ISO string
                - budget: Optional ChunkBudget parameters
                - model: Optional model identifier
                - force_regenerate: bool to supersede existing blocks
        """
        # Parse input
        if isinstance(data, dict):
            start_time = self._parse_datetime(data.get("start_time"))
            end_time = self._parse_datetime(data.get("end_time"))
            model = data.get("model")
            force_regenerate = data.get("force_regenerate", False)
            
            # Parse budget if provided
            budget_params = data.get("budget", {})
            budget = ChunkBudget(**budget_params) if budget_params else None
        else:
            # Default: process yesterday
            end_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            start_time = end_time - timedelta(days=1)
            model = None
            force_regenerate = False
            budget = None
        
        logger.info(
            f"Timeline enricher processing period: {start_time} to {end_time}"
        )
        
        async with async_session() as session:
            # Find self in database
            stmt_actor = select(models.Actor).where(
                models.Actor.slug == "timeline-enricher"
            ).order_by(models.Actor.id.desc()).limit(1)
            actor = (await session.exec(stmt_actor)).first()
            
            if not actor or actor.id is None:
                logger.error("Timeline enricher actor not found in DB")
                return {"status": "error", "message": "Actor not found"}
            
            # Step 1: Chunk events
            logger.info("Chunking events...")
            chunks = await TimelineChunkingService.chunk_events_for_period(
                session,
                start_time,
                end_time,
                budget=budget
            )
            
            if not chunks:
                logger.info("No events to process")
                return {
                    "status": "success",
                    "message": "No events found in period",
                    "blocks_created": 0
                }
            
            # Step 2: Generate timeline blocks
            logger.info(f"Generating timeline blocks for {len(chunks)} chunks...")
            blocks = await TimelineGenerationService.generate_timeline_blocks_for_period(
                session,
                chunks,
                actor_id=actor.id,
                model=model
            )
            
            # Step 3: Supersede old blocks if regenerating
            if force_regenerate and blocks:
                logger.info("Superseding existing blocks...")
                superseded = await TimelineGenerationService.supersede_blocks_for_period(
                    session,
                    start_time,
                    end_time,
                    actor_id=actor.id,
                    new_blocks=blocks
                )
                logger.info(f"Superseded {len(superseded)} old blocks")
            
            logger.info(f"Timeline enrichment complete: {len(blocks)} blocks created")
            
            return {
                "status": "success",
                "blocks_created": len(blocks),
                "chunks_processed": len(chunks),
                "period": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat()
                }
            }
    
    def _parse_datetime(self, dt: Any) -> datetime:
        """Parse datetime from various formats."""
        if isinstance(dt, datetime):
            return dt
        if isinstance(dt, str):
            # Handle ISO format
            if dt.endswith('Z'):
                dt = dt[:-1] + '+00:00'
            try:
                parsed = datetime.fromisoformat(dt)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except Exception:
                pass
        # Default: now
        return datetime.now(timezone.utc)

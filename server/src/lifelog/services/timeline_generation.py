"""
Timeline Generation Service

Uses LLM to generate enriched timeline blocks from event chunks.
Handles prompt templating, model versioning, and block persistence.
"""

import logging
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from .. import models
from ..core.ai import ai_service
from .chunking import EventChunk

logger = logging.getLogger(__name__)


# Default prompt template for timeline block generation
DEFAULT_TIMELINE_PROMPT = """You are an AI assistant helping to create a personal life log timeline. 

Given a list of chronological events, create a concise timeline entry that:
1. Combines related events into a coherent narrative
2. Provides context by weaving together different data sources (e.g., GPS, banking, computer activity)
3. Highlights the main activity without being too verbose
4. Includes a short, descriptive title
5. Extracts relevant metadata tags for searchability

Events:
{events_text}

Respond with a JSON object with this structure:
{{
  "title": "Short descriptive title (3-7 words)",
  "summary": "Human-readable narrative combining the context from events (2-4 sentences)",
  "tags": ["tag1", "tag2", "tag3"],
  "metadata": {{
    "location": "primary location if evident",
    "main_activity": "primary activity category",
    "tools_used": ["applications", "websites", "etc"],
    "context_notes": "any other relevant context"
  }}
}}

Focus on what matters - the bigger picture, not minute details. Make it easy to understand what happened during this time."""


class TimelineGenerationService:
    """Service for generating timeline blocks using LLM."""
    
    @staticmethod
    async def generate_timeline_block(
        session: AsyncSession,
        chunk: EventChunk,
        actor_id: int,
        provider_slug: Optional[str] = None,
        model: Optional[str] = None,
        prompt_template: Optional[str] = None,
        prompt_template_id: Optional[int] = None
    ) -> models.TimelineBlock:
        """
        Generate a timeline block from an event chunk using LLM.
        
        Args:
            session: Database session
            chunk: EventChunk containing events to summarize
            actor_id: ID of the enricher actor generating this block
            provider_slug: AI provider slug (uses default if None)
            model: Model identifier (uses default if None)
            prompt_template: Custom prompt template text
            prompt_template_id: ID of prompt template in database
        
        Returns:
            Created TimelineBlock model instance
        """
        # Resolve prompt template
        if prompt_template_id:
            stmt = select(models.PromptTemplate).where(
                models.PromptTemplate.id == prompt_template_id
            )
            template_record = (await session.exec(stmt)).one_or_none()
            if template_record:
                prompt_template = template_record.template_text
        
        if not prompt_template:
            prompt_template = DEFAULT_TIMELINE_PROMPT
        
        # Format prompt with events
        events_text = chunk.to_text()
        formatted_prompt = prompt_template.format(events_text=events_text)
        
        # Get AI settings
        from ..core.config import settings
        db_settings = (
            await session.exec(
                select(models.AISettings).where(models.AISettings.id == 1)
            )
        ).one_or_none()
        
        # Resolve provider and model
        # For completions, we need a chat-capable provider, not an embedding provider
        # Use litellm as default, which supports chat completions
        provider_slug_final = provider_slug or "litellm"
        model_final = model or getattr(settings, "DEFAULT_CHAT_MODEL", "gpt-3.5-turbo")
        
        logger.info(
            f"Generating timeline block for {len(chunk.events)} events "
            f"using {provider_slug_final}/{model_final}"
        )
        
        # Call LLM
        try:
            response_text, usage_log_id = await ai_service.generate_completion(
                session,
                provider_slug=provider_slug_final,
                model=model_final,
                prompt=formatted_prompt,
                actor_id=actor_id
            )
            
            # Parse JSON response
            response_data = json.loads(response_text.strip())
            
            # Extract fields
            title = response_data.get("title", "Untitled Activity")
            summary = response_data.get("summary", "No summary available")
            tags = response_data.get("tags", [])
            metadata = response_data.get("metadata", {})
            
            # Build block_data with all context
            block_data = {
                "metadata": metadata,
                "source_event_count": len(chunk.events),
                "time_span_minutes": chunk.duration().total_seconds() / 60,
                "generation_timestamp": datetime.utcnow().isoformat()
            }
            
            # Create timeline block
            timeline_block = models.TimelineBlock(
                actor_id=actor_id,
                start_time=chunk.start_time,
                end_time=chunk.end_time,
                title=title,
                summary=summary,
                tags=tags,
                block_data=block_data,
                character_count=chunk.character_count,
                token_count=None,  # Could extract from usage_log if available
                model_version=model_final,
                prompt_template_id=prompt_template_id,
                ai_usage_log_id=usage_log_id
            )
            
            # Persist block
            session.add(timeline_block)
            await session.flush()
            await session.refresh(timeline_block)
            
            # Link to source events
            if timeline_block.id:
                for event_id in chunk.event_ids:
                    link = models.TimelineBlockEventLink(
                        timeline_block_id=timeline_block.id,
                        event_id=event_id
                    )
                    session.add(link)
            
            await session.commit()
            await session.refresh(timeline_block)
            
            logger.info(f"Created timeline block {timeline_block.id}: {title}")
            return timeline_block
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Response was: {response_text[:500]}")
            raise ValueError(f"LLM returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Failed to generate timeline block: {e}")
            raise
    
    @staticmethod
    async def generate_timeline_blocks_for_period(
        session: AsyncSession,
        chunks: List[EventChunk],
        actor_id: int,
        provider_slug: Optional[str] = None,
        model: Optional[str] = None,
        prompt_template_id: Optional[int] = None
    ) -> List[models.TimelineBlock]:
        """
        Generate timeline blocks for multiple chunks.
        
        Args:
            session: Database session
            chunks: List of EventChunks to process
            actor_id: ID of the enricher actor
            provider_slug: AI provider slug
            model: Model identifier
            prompt_template_id: Prompt template ID
        
        Returns:
            List of created TimelineBlock instances
        """
        blocks = []
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)}")
            try:
                block = await TimelineGenerationService.generate_timeline_block(
                    session,
                    chunk,
                    actor_id,
                    provider_slug=provider_slug,
                    model=model,
                    prompt_template_id=prompt_template_id
                )
                blocks.append(block)
            except Exception as e:
                logger.error(f"Failed to generate block for chunk {i+1}: {e}")
                # Continue with remaining chunks
                continue
        
        logger.info(f"Generated {len(blocks)}/{len(chunks)} timeline blocks")
        return blocks
    
    @staticmethod
    async def supersede_blocks_for_period(
        session: AsyncSession,
        start_time: datetime,
        end_time: datetime,
        actor_id: int,
        new_blocks: List[models.TimelineBlock]
    ) -> List[int]:
        """
        Supersede existing timeline blocks in a period with new ones.
        
        This is used when regenerating timeline blocks (e.g., with new model/prompt).
        
        Args:
            session: Database session
            start_time: Start of period
            end_time: End of period
            actor_id: Actor ID that generated the blocks
            new_blocks: Newly generated blocks
        
        Returns:
            List of superseded block IDs
        """
        # Find existing non-superseded blocks in the period
        stmt = (
            select(models.TimelineBlock)
            .where(models.TimelineBlock.start_time >= start_time)
            .where(models.TimelineBlock.end_time <= end_time)
            .where(models.TimelineBlock.actor_id == actor_id)
            .where(models.TimelineBlock.superseded_by_block_id.is_(None))  # type: ignore[attr-defined]
        )
        result = await session.exec(stmt)
        existing_blocks = list(result.all())
        
        if not existing_blocks:
            logger.info("No existing blocks to supersede")
            return []
        
        superseded_ids = []
        
        # For simplicity, we'll supersede all old blocks with the first new block
        # In a more sophisticated system, you might match blocks by time overlap
        if new_blocks:
            superseding_block_id = new_blocks[0].id
            
            for old_block in existing_blocks:
                if old_block.id:
                    old_block.superseded_by_block_id = superseding_block_id
                    session.add(old_block)
                    superseded_ids.append(old_block.id)
            
            await session.commit()
            logger.info(f"Superseded {len(superseded_ids)} existing blocks")
        
        return superseded_ids

"""
Timeline Blocks API endpoints

Provides access to AI-generated timeline blocks (enrichment artifacts).
"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from pydantic import BaseModel

from ..dependencies import get_session
from ..auth import require_auth
from .. import models


router = APIRouter(
    prefix="/timeline-blocks",
    tags=["Timeline Blocks"],
)


class TimelineBlockResponse(BaseModel):
    """Timeline block model for client consumption."""
    id: int
    start_time: datetime
    end_time: datetime
    title: str
    summary: str
    tags: Optional[List[str]]
    metadata: dict
    model_version: str
    created_at: datetime
    source_event_count: int


@router.get("/", response_model=List[TimelineBlockResponse])
async def get_timeline_blocks(
    start_time: Optional[datetime] = Query(None, description="Filter blocks starting from this time"),
    end_time: Optional[datetime] = Query(None, description="Filter blocks ending before this time"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of blocks to return"),
    skip: int = Query(0, ge=0, description="Number of blocks to skip"),
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Get timeline blocks (AI-generated enriched summaries).
    
    Timeline blocks are enrichment artifacts that combine multiple events
    into concise, context-aware summaries. They represent higher-level
    activities and provide a better overview than raw events.
    
    Only returns non-superseded blocks (latest versions).
    """
    # Build query for non-superseded blocks
    query = select(models.TimelineBlock).where(
        models.TimelineBlock.superseded_by_block_id.is_(None)  # type: ignore[attr-defined]
    )
    
    # Apply time filters if provided
    if start_time:
        query = query.where(models.TimelineBlock.start_time >= start_time)
    if end_time:
        query = query.where(models.TimelineBlock.end_time <= end_time)
    
    # Order by start time (most recent first) and apply pagination
    query = query.order_by(models.TimelineBlock.start_time.desc()).offset(skip).limit(limit)  # type: ignore[attr-defined]
    
    result = await session.exec(query)
    blocks = list(result.all())
    
    # Convert to response model
    timeline_blocks = []
    for block in blocks:
        timeline_blocks.append(TimelineBlockResponse(
            id=block.id,  # type: ignore[arg-type]
            start_time=block.start_time,
            end_time=block.end_time,
            title=block.title,
            summary=block.summary,
            tags=block.tags,
            metadata=block.block_data.get("metadata", {}),
            model_version=block.model_version,
            created_at=block.created_at,
            source_event_count=block.block_data.get("source_event_count", 0)
        ))
    
    return timeline_blocks


@router.get("/{block_id}", response_model=TimelineBlockResponse)
async def get_timeline_block(
    block_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """Get a specific timeline block by ID."""
    # Get block (only if not superseded)
    query = select(models.TimelineBlock).where(
        models.TimelineBlock.id == block_id,
        models.TimelineBlock.superseded_by_block_id.is_(None)  # type: ignore[attr-defined]
    )
    
    result = await session.exec(query)
    block = result.first()
    
    if not block:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Timeline block not found or has been superseded"
        )
    
    return TimelineBlockResponse(
        id=block.id,  # type: ignore[arg-type]
        start_time=block.start_time,
        end_time=block.end_time,
        title=block.title,
        summary=block.summary,
        tags=block.tags,
        metadata=block.block_data.get("metadata", {}),
        model_version=block.model_version,
        created_at=block.created_at,
        source_event_count=block.block_data.get("source_event_count", 0)
    )


@router.get("/{block_id}/events", response_model=List[int])
async def get_block_source_events(
    block_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Get the IDs of source events that were used to generate this timeline block.
    
    This allows tracing back to the original events for detailed investigation.
    """
    # Verify block exists
    block = await session.get(models.TimelineBlock, block_id)
    if not block:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Timeline block not found"
        )
    
    # Get linked events via association table
    stmt = (
        select(models.TimelineBlockEventLink.event_id)
        .where(models.TimelineBlockEventLink.timeline_block_id == block_id)
    )
    result = await session.exec(stmt)
    event_ids = [row for row in result.all()]
    
    return event_ids

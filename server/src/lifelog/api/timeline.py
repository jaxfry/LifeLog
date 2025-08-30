"""
Timeline API endpoints for LifeLog Client Data API.

Provides timeline data for client applications as specified in the architecture.
"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from pydantic import BaseModel

from ..dependencies import get_session
from ..auth import require_auth
from .. import models


router = APIRouter(
    prefix="/timeline",
    tags=["Timeline"],
)


class TimelineEvent(BaseModel):
    """Timeline event model for client consumption"""
    id: int
    start_time: datetime
    end_time: Optional[datetime]
    event_type: str
    summary: Optional[str]
    

@router.get("/", response_model=List[TimelineEvent])
async def get_timeline(
    start_time: Optional[datetime] = Query(None, description="Filter events starting from this time"),
    end_time: Optional[datetime] = Query(None, description="Filter events ending before this time"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events to return"),
    skip: int = Query(0, ge=0, description="Number of events to skip"),
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Get timeline events for the authenticated user.
    
    This endpoint provides the main timeline data for client applications,
    returning only non-superseded events as per the architecture.
    """
    # Build the query - only non-superseded events
    query = select(models.Event).where(models.Event.superseded_by_event_id.is_(None))
    
    # Apply time filters if provided
    if start_time:
        query = query.where(models.Event.start_time >= start_time)
    if end_time:
        query = query.where(models.Event.start_time <= end_time)
    
    # Order by start time (most recent first) and apply pagination
    query = query.order_by(models.Event.start_time.desc()).offset(skip).limit(limit)
    
    result = await session.exec(query)
    events = result.all()
    
    # Convert to response model
    timeline_events = []
    for event in events:
        # Get event type name (need to load the relationship)
        event_type_query = select(models.EventType).where(models.EventType.id == event.event_type_id)
        event_type_result = await session.exec(event_type_query)
        event_type = event_type_result.first()
        event_type_name = event_type.slug if event_type else "unknown"
        
        timeline_events.append(TimelineEvent(
            id=event.id,
            start_time=event.start_time,
            end_time=event.end_time,
            event_type=event_type_name,
            summary=event.summary
        ))
    
    return timeline_events


@router.get("/{event_id}")
async def get_timeline_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """Get a specific timeline event by ID"""
    # Only return non-superseded events
    query = select(models.Event).where(
        models.Event.id == event_id,
        models.Event.superseded_by_event_id.is_(None)
    )
    
    result = await session.exec(query)
    event = result.first()
    
    if not event:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found or has been superseded"
        )
    
    # Get event type name
    event_type_query = select(models.EventType).where(models.EventType.id == event.event_type_id)
    event_type_result = await session.exec(event_type_query)
    event_type = event_type_result.first()
    event_type_name = event_type.slug if event_type else "unknown"
    
    return TimelineEvent(
        id=event.id,
        start_time=event.start_time,
        end_time=event.end_time,
        event_type=event_type_name,
        summary=event.summary
    )
"""
Timeline API endpoints for LifeLog Client Data API.

Provides timeline data for client applications as specified in the architecture.
Uses service layer to abstract database operations.
"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel

from ..dependencies import get_session
from ..auth import require_auth
from ..services.timeline import TimelineService


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
    # Use service layer to get events
    events = await TimelineService.get_timeline_events(
        session, start_time, end_time, limit, skip
    )
    
    # Convert to response model
    timeline_events = []
    for event in events:
        # Get event type name using service layer
        event_type_name = await TimelineService.get_event_type_name(session, event.event_type_id)
        
        timeline_events.append(TimelineEvent(
            id=event.id,
            start_time=event.start_time,
            end_time=event.end_time,
            event_type=event_type_name,
            summary=event.summary
        ))
    
    return timeline_events


@router.get("/{event_id}", response_model=TimelineEvent)
async def get_timeline_event(
    event_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """Get a specific timeline event by ID"""
    # Use service layer to get event
    event = await TimelineService.get_event_by_id(session, event_id)
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found or has been superseded"
        )
    
    # Get event type name using service layer
    event_type_name = await TimelineService.get_event_type_name(session, event.event_type_id)
    
    return TimelineEvent(
        id=event.id,
        start_time=event.start_time,
        end_time=event.end_time,
        event_type=event_type_name,
        summary=event.summary
    )
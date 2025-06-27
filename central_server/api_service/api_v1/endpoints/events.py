import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from central_server.api_service import schemas
from central_server.api_service.core.database import get_db
from central_server.api_service.core.models import Event as EventModel, DigitalActivityData
from central_server.api_service.auth import get_current_active_user

router = APIRouter()

async def get_event_by_id(db: AsyncSession, event_id: uuid.UUID) -> EventModel:
    result = await db.execute(select(EventModel).where(EventModel.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event

async def get_event_payload(db: AsyncSession, event: EventModel) -> Dict[str, Any]:
    # Example for digital_activity, can be extended for other event types
    if event.event_type == "digital_activity" and event.digital_activity:
        return {
            "hostname": event.digital_activity.hostname,
            "app": event.digital_activity.app,
            "title": event.digital_activity.title,
            "url": event.digital_activity.url,
        }
    # Add more event_type-specific payloads here
    return event.details or {}

@router.get("", response_model=List[schemas.Event])
async def read_events(
    start_time: Optional[datetime] = Query(None, description="Filter by start time (ISO 8601). Inclusive."),
    end_time: Optional[datetime] = Query(None, description="Filter by end time (ISO 8601). Inclusive of event start times within this."),
    source: Optional[str] = Query(None, description="Filter by event source."),
    event_type: Optional[str] = Query(None, description="Filter by event type."),
    skip: int = Query(0, ge=0, description="Number of items to skip."),
    limit: int = Query(100, ge=1, le=500, description="Number of items to return."),
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user)
):
    query = select(EventModel)
    if start_time:
        query = query.where(EventModel.start_time >= start_time)
    if end_time:
        query = query.where(EventModel.start_time <= end_time)
    if source:
        query = query.where(EventModel.source == source)
    if event_type:
        query = query.where(EventModel.event_type == event_type)
    query = query.order_by(EventModel.start_time.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    events = result.scalars().all()
    out = []
    for event in events:
        payload = await get_event_payload(db, event)
        out.append(schemas.Event(
            id=event.id,
            event_type=event.event_type,
            source=event.source,
            start_time=event.start_time,
            end_time=event.end_time,
            payload_hash=event.payload_hash,
            local_day=event.local_day,
            user_id=event.user_id,
            details=payload
        ))
    return out

@router.get("/{event_id}", response_model=schemas.Event)
async def read_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user)
):
    event = await get_event_by_id(db, event_id)
    payload = await get_event_payload(db, event)
    return schemas.Event(
        id=event.id,
        event_type=event.event_type,
        source=event.source,
        start_time=event.start_time,
        end_time=event.end_time,
        payload_hash=event.payload_hash,
        local_day=event.local_day,
        user_id=event.user_id,
        details=payload
    )
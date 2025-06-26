import uuid
from typing import List, Optional, Annotated, Dict, Any
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import APIRouter, Depends, HTTPException, status, Query

from backend.app import schemas
from backend.app.core.db import get_db
from backend.app.api_v1.auth import get_current_active_user
from backend.app.models import Event as EventModel, DigitalActivityData

router = APIRouter()

CurrentUserDep = Annotated[schemas.User, Depends(get_current_active_user)]
DBDep = Annotated[AsyncSession, Depends(get_db)]

async def _map_event_row_to_schema(db: AsyncSession, event_obj: EventModel) -> Optional[schemas.Event]:
    if not event_obj:
        return None
    actual_payload: Dict[str, Any] = {"placeholder": "Payload data would be here, fetched based on event_type and event_id"}
    if event_obj.event_type == 'digital_activity':
        result = await db.execute(
            select(DigitalActivityData).where(DigitalActivityData.event_id == event_obj.id)
        )
        digital_data = result.scalar_one_or_none()
        if digital_data:
            actual_payload = {
                "hostname": digital_data.hostname,
                "app": digital_data.app,
                "title": digital_data.title,
                "url": digital_data.url,
            }
        else:
            actual_payload = {"info": "No detailed digital activity data found for this event_id."}
    return schemas.Event(
        id=event_obj.id,
        source=event_obj.source,
        event_type=event_obj.event_type,
        start_time=event_obj.start_time,
        end_time=event_obj.end_time,
        payload=actual_payload,
        local_day=event_obj.local_day
    )

async def get_event_db(db: AsyncSession, event_id: uuid.UUID) -> Optional[schemas.Event]:
    result = await db.execute(select(EventModel).where(EventModel.id == event_id))
    event_obj = result.scalar_one_or_none()
    if event_obj:
        return await _map_event_row_to_schema(db, event_obj)
    return None

async def get_events_db(
    db: AsyncSession,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    source: Optional[str] = None,
    event_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
) -> List[schemas.Event]:
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
    event_objs = result.scalars().all()
    events: List[schemas.Event] = []
    for event_obj in event_objs:
        mapped_event = await _map_event_row_to_schema(db, event_obj)
        if mapped_event:
            events.append(mapped_event)
    return events

@router.get("", response_model=List[schemas.Event])
async def read_events(
    db: DBDep,
    current_user: CurrentUserDep,
    start_time: Optional[datetime] = Query(None, description="Filter by start time (ISO 8601). Inclusive."),
    end_time: Optional[datetime] = Query(None, description="Filter by end time (ISO 8601). Inclusive of event start times within this."),
    source: Optional[str] = Query(None, description="Filter by event source (e.g., 'activitywatch_aw-watcher-window')."),
    event_type: Optional[str] = Query(None, description="Filter by event type (e.g., 'digital_activity')."),
    skip: int = Query(0, ge=0, description="Number of items to skip."),
    limit: int = Query(100, ge=1, le=500, description="Number of items to return.")
):
    """
    Retrieve raw events with filtering and pagination.
    Events are generally immutable post-ingestion.
    The 'payload' field currently contains a placeholder or basic data; full payload reconstruction is complex.
    """
    events_list = await get_events_db(db, start_time, end_time, source, event_type, skip, limit)
    return events_list

@router.get("/{event_id}", response_model=schemas.Event)
async def read_event(
    event_id: uuid.UUID,
    db: DBDep,
    current_user: CurrentUserDep
):
    """
    Get a specific raw event by its ID.
    The 'payload' field currently contains a placeholder or basic data.
    """
    db_event = await get_event_db(db, event_id)
    if db_event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return db_event

# POST, PUT, DELETE for events are intentionally omitted as per design plan (events are immutable post-ingestion)
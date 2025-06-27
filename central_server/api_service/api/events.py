from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from datetime import datetime, date
import uuid

from central_server.api_service.core.database import get_db
from central_server.api_service.core.models import Event as EventModel, DigitalActivityData
from central_server.api_service.auth import get_current_active_user
from central_server.api_service import schemas

router = APIRouter()

async def get_event_by_id(db: AsyncSession, event_id: uuid.UUID) -> EventModel:
    """Get an event by ID"""
    result = await db.execute(
        select(EventModel)
        .options(selectinload(EventModel.digital_activity))
        .where(EventModel.id == event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )
    return event

@router.get("", response_model=List[schemas.Event])
async def get_events(
    start_time: Optional[datetime] = Query(None, description="Filter by start time (inclusive)"),
    end_time: Optional[datetime] = Query(None, description="Filter by end time (inclusive)"),
    source: Optional[str] = Query(None, description="Filter by source"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of items to return"),
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user)
):
    """Get events with filtering and pagination"""
    query = select(EventModel).options(selectinload(EventModel.digital_activity))
    
    # Apply filters
    conditions = []
    if start_time:
        conditions.append(EventModel.start_time >= start_time)
    if end_time:
        conditions.append(EventModel.start_time <= end_time)
    if source:
        conditions.append(EventModel.source == source)
    if event_type:
        conditions.append(EventModel.event_type == event_type)
    
    if conditions:
        query = query.where(and_(*conditions))
    
    # Apply sorting and pagination
    query = query.order_by(EventModel.start_time.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    events = result.scalars().all()
    
    return [schemas.Event.model_validate(event) for event in events]

@router.get("/{event_id}", response_model=schemas.Event)
async def get_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user)
):
    """Get an event by ID"""
    event = await get_event_by_id(db, event_id)
    return schemas.Event.model_validate(event)

@router.get("/stats/summary")
async def get_event_stats(
    start_date: Optional[date] = Query(None, description="Filter by start date (inclusive)"),
    end_date: Optional[date] = Query(None, description="Filter by end date (inclusive)"),
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user)
):
    """Get event statistics"""
    query = select(func.count(EventModel.id))
    
    # Apply date filters
    conditions = []
    if start_date:
        conditions.append(EventModel.local_day >= start_date)
    if end_date:
        conditions.append(EventModel.local_day <= end_date)
    
    if conditions:
        query = query.where(and_(*conditions))
    
    result = await db.execute(query)
    total_events = result.scalar()
    
    # Get events by type
    type_query = select(EventModel.event_type, func.count(EventModel.id))
    if conditions:
        type_query = type_query.where(and_(*conditions))
    type_query = type_query.group_by(EventModel.event_type)
    
    type_result = await db.execute(type_query)
    events_by_type = dict(type_result.all())
    
    return {
        "total_events": total_events,
        "events_by_type": events_by_type,
        "date_range": {
            "start_date": start_date,
            "end_date": end_date
        }
    }

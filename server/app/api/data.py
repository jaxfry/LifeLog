from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col
from app.core.db import get_session
from app.models.data import RawLog, Event, Timeline, Session
from app.api.deps import Pagination

router = APIRouter()

# --- Timeline Endpoints ---

@router.get("/timeline", response_model=List[Timeline])
async def get_timeline(
    pagination: Pagination = Depends(),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    session: AsyncSession = Depends(get_session)
):
    """
    Retrieve processed timeline entries (the AI story).
    """
    query = select(Timeline).order_by(col(Timeline.start_time).desc())
    
    if start_date:
        query = query.where(Timeline.start_time >= start_date)
        
    if end_date:
        query = query.where(Timeline.end_time <= end_date)
        
    query = query.offset(pagination.offset).limit(pagination.limit)
    
    result = await session.execute(query)
    return result.scalars().all()

@router.get("/sessions", response_model=List[Session])
async def get_sessions(
    pagination: Pagination = Depends(),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    """
    Retrieve sessions (groups of events).
    """
    query = select(Session).order_by(col(Session.start_time).desc())
    
    if start_date:
        query = query.where(Session.start_time >= start_date)
        
    if end_date:
        query = query.where(Session.end_time <= end_date)
        
    if status:
        query = query.where(Session.status == status)
        
    query = query.offset(pagination.offset).limit(pagination.limit)
    
    result = await session.execute(query)
    return result.scalars().all()

# --- Raw Data Endpoints ---

@router.get("/logs", response_model=List[RawLog])
async def get_logs(
    pagination: Pagination = Depends(),
    extension_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    session: AsyncSession = Depends(get_session)
):
    query = select(RawLog).order_by(col(RawLog.received_at).desc())
    
    if extension_id:
        query = query.where(RawLog.extension_id == extension_id)
    
    if start_date:
        query = query.where(RawLog.received_at >= start_date)
        
    if end_date:
        query = query.where(RawLog.received_at <= end_date)
        
    query = query.offset(pagination.offset).limit(pagination.limit)
    
    result = await session.execute(query)
    return result.scalars().all()

@router.get("/events", response_model=List[Event])
async def get_events(
    pagination: Pagination = Depends(),
    extension_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    session: AsyncSession = Depends(get_session)
):
    # If filtering by extension_id, we need to join with RawLog
    if extension_id:
        query = select(Event).join(RawLog).where(RawLog.extension_id == extension_id)
    else:
        query = select(Event)
        
    # Filter out superseded events
    query = query.where(Event.is_superseded == False)
        
    query = query.order_by(col(Event.created_at).desc())
    
    if start_date:
        query = query.where(Event.created_at >= start_date)
        
    if end_date:
        query = query.where(Event.created_at <= end_date)
        
    query = query.offset(pagination.offset).limit(pagination.limit)
    
    result = await session.execute(query)
    return result.scalars().all()


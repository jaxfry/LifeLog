from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col
from app.core.db import get_session
from app.models.data import RawLog, Event, Timeline, Session, DailyChapter, DailySummary
from app.api.deps import Pagination

router = APIRouter()

def normalize_datetime(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Ensure datetime is naive UTC for database comparison.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt

# --- Timeline Endpoints ---

@router.get("/chapters", response_model=List[DailyChapter])
async def get_chapters(
    pagination: Pagination = Depends(),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    session: AsyncSession = Depends(get_session)
):
    """
    Retrieve daily chapters.
    """
    start_date = normalize_datetime(start_date)
    end_date = normalize_datetime(end_date)
    
    query = select(DailyChapter).order_by(col(DailyChapter.start_time).desc())
    
    if start_date:
        query = query.where(DailyChapter.start_time >= start_date)
        
    if end_date:
        query = query.where(DailyChapter.end_time <= end_date)
        
    query = query.offset(pagination.offset).limit(pagination.limit)
    
    result = await session.execute(query)
    return result.scalars().all()

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
    start_date = normalize_datetime(start_date)
    end_date = normalize_datetime(end_date)

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
    start_date = normalize_datetime(start_date)
    end_date = normalize_datetime(end_date)

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
    start_date = normalize_datetime(start_date)
    end_date = normalize_datetime(end_date)

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
    start_date = normalize_datetime(start_date)
    end_date = normalize_datetime(end_date)

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

# --- Daily Summaries Endpoints ---

@router.get("/summaries", response_model=List[DailySummary])
async def get_summaries(
    pagination: Pagination = Depends(),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    session: AsyncSession = Depends(get_session)
):
    """
    Retrieve daily summaries.
    """
    start_date = normalize_datetime(start_date)
    end_date = normalize_datetime(end_date)

    query = select(DailySummary).order_by(col(DailySummary.date).desc())
    
    if start_date:
        query = query.where(DailySummary.date >= start_date)
        
    if end_date:
        query = query.where(DailySummary.date <= end_date)
        
    query = query.offset(pagination.offset).limit(pagination.limit)
    
    result = await session.execute(query)
    return result.scalars().all()

@router.get("/summaries/{date}", response_model=Optional[DailySummary])
async def get_summary_by_date(
    date: str,  # YYYY-MM-DD format
    session: AsyncSession = Depends(get_session)
):
    """
    Retrieve a specific daily summary by date.
    """
    # Parse the date string
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    result = await session.get(DailySummary, date_obj)
    return result


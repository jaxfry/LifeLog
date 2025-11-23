from typing import List, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, text
from sqlmodel import select, col
from app.core.db import get_session
from app.models.data import Session, Event, Timeline

router = APIRouter()

@router.get("/stats")
async def get_stats(session: AsyncSession = Depends(get_session)):
    """
    Get overall statistics for the dashboard.
    """
    # Total counts
    total_sessions_query = select(func.count()).select_from(Session)
    total_events_query = select(func.count()).select_from(Event)
    
    total_sessions = (await session.execute(total_sessions_query)).scalar_one()
    total_events = (await session.execute(total_events_query)).scalar_one()
    
    # Calculate average sessions per day (over all time)
    # First get the date range
    min_date_query = select(func.min(Session.start_time))
    max_date_query = select(func.max(Session.start_time))
    
    min_date = (await session.execute(min_date_query)).scalar_one()
    max_date = (await session.execute(max_date_query)).scalar_one()
    
    avg_sessions_per_day = 0
    if min_date and max_date:
        days = (max_date - min_date).days + 1
        if days > 0:
            avg_sessions_per_day = round(total_sessions / days, 1)
            
    return {
        "total_sessions": total_sessions,
        "total_events": total_events,
        "avg_sessions_per_day": avg_sessions_per_day,
        "first_activity_date": min_date,
        "last_activity_date": max_date
    }

@router.get("/activity-volume")
async def get_activity_volume(
    days: int = Query(7, ge=1, le=365),
    session: AsyncSession = Depends(get_session)
):
    """
    Get activity volume (session counts) per day for the last N days.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Group by date
    # Note: This assumes PostgreSQL for date_trunc
    query = (
        select(
            func.date_trunc('day', Session.start_time).label('date'),
            func.count(Session.id).label('count')
        )
        .where(Session.start_time >= start_date)
        .group_by(text('date'))
        .order_by(text('date'))
    )
    
    result = await session.execute(query)
    rows = result.all()
    
    # Fill in missing days with 0
    data = {}
    for row in rows:
        date_str = row.date.strftime('%Y-%m-%d')
        data[date_str] = row.count
        
    filled_data = []
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        filled_data.append({
            "date": date_str,
            "count": data.get(date_str, 0)
        })
        current_date += timedelta(days=1)
        
    return filled_data

@router.get("/status-distribution")
async def get_status_distribution(session: AsyncSession = Depends(get_session)):
    """
    Get the distribution of session statuses.
    """
    query = (
        select(Session.status, func.count())
        .group_by(Session.status)
    )
    
    result = await session.execute(query)
    rows = result.all()
    
    return [{"name": row[0], "value": row[1]} for row in rows]

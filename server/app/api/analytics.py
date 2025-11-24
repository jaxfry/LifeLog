from typing import List, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, text
from sqlmodel import select, col
from app.core.db import get_session
from app.models.data import Session, Event, Timeline, RawLog
from app.models.config import Device, Extension

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

@router.get("/dashboard-metrics")
async def get_dashboard_metrics(session: AsyncSession = Depends(get_session)):
    """
    Get comprehensive metrics for the dashboard page.
    """
    # Total events
    total_events_query = select(func.count()).select_from(Event).where(Event.is_superseded == False)
    total_events = (await session.execute(total_events_query)).scalar_one()
    
    # Active collectors (extensions that are active)
    active_collectors_query = select(func.count()).select_from(Extension).where(Extension.is_active == True)
    active_collectors = (await session.execute(active_collectors_query)).scalar_one()
    
    # AI processing stats (timeline entries)
    ai_processing_query = select(func.count()).select_from(Timeline)
    ai_processing = (await session.execute(ai_processing_query)).scalar_one()
    
    # Storage used (estimate based on raw logs)
    # Using pg_column_size if available, otherwise approximate
    try:
        storage_query = select(func.sum(func.length(func.cast(RawLog.payload, text))))
        storage_result = await session.execute(storage_query)
        storage_bytes = storage_result.scalar_one() or 0
        storage_mb = round(storage_bytes / (1024 * 1024), 2)
    except:
        # Fallback if the above doesn't work
        storage_mb = 0
    
    # Activity volume for last 7 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    activity_query = (
        select(
            func.date_trunc('day', Session.start_time).label('date'),
            func.count(Session.id).label('count')
        )
        .where(Session.start_time >= start_date)
        .group_by(text('date'))
        .order_by(text('date'))
    )
    
    result = await session.execute(activity_query)
    rows = result.all()
    
    activity_volume = []
    current_date = start_date
    data = {row.date.strftime('%Y-%m-%d'): row.count for row in rows}
    
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        activity_volume.append({
            "date": date_str,
            "count": data.get(date_str, 0)
        })
        current_date += timedelta(days=1)
    
    return {
        "total_events": total_events,
        "active_collectors": active_collectors,
        "ai_processing": ai_processing,
        "storage_used_mb": storage_mb,
        "activity_volume": activity_volume
    }

@router.get("/collector-stats")
async def get_collector_stats(session: AsyncSession = Depends(get_session)):
    """
    Get statistics about collectors per device.
    """
    # Get all devices
    devices_query = select(Device)
    devices_result = await session.execute(devices_query)
    devices = devices_result.scalars().all()
    
    device_stats = []
    for device in devices:
        # Count logs from this device in last 24 hours
        recent_cutoff = datetime.now() - timedelta(hours=24)
        logs_query = select(func.count()).select_from(RawLog).where(
            RawLog.device_id == device.id,
            RawLog.received_at >= recent_cutoff
        )
        recent_logs = (await session.execute(logs_query)).scalar_one()
        
        # Get unique extensions for this device
        extensions_query = select(func.count(func.distinct(RawLog.extension_id))).select_from(RawLog).where(
            RawLog.device_id == device.id
        )
        extension_count = (await session.execute(extensions_query)).scalar_one()
        
        device_stats.append({
            "device_id": device.id,
            "device_name": device.name,
            "device_type": device.type,
            "collectors_count": extension_count,
            "recent_activity": recent_logs > 0,
            "last_cursor": device.last_cursor
        })
    
    return device_stats

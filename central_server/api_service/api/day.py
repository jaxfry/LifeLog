from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func 
from sqlalchemy.orm import selectinload
from datetime import date, datetime, timedelta

from central_server.api_service.core.database import get_db
from central_server.api_service.core.models import TimelineEntry as TimelineEntryModel, Event as EventModel, Project as ProjectModel
from central_server.api_service.auth import get_current_active_user
from central_server.api_service import schemas

router = APIRouter()

def validate_date_string(date_string: str) -> date:
    """Validate and parse date string"""
    try:
        return datetime.strptime(date_string, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid date format. Use YYYY-MM-DD"
        )

async def get_timeline_entries_for_date(db: AsyncSession, target_date: date) -> List[TimelineEntryModel]:
    """Get timeline entries for a specific date"""
    result = await db.execute(
        select(TimelineEntryModel)
        .options(selectinload(TimelineEntryModel.project))
        .where(TimelineEntryModel.local_day == target_date)
        .order_by(TimelineEntryModel.start_time)
    )
    return list(result.scalars().all())

async def calculate_day_stats(db: AsyncSession, target_date: date) -> schemas.DayStats:
    """Calculate statistics for a day"""
    # Get timeline entries for the day
    timeline_entries = await get_timeline_entries_for_date(db, target_date)
    
    if not timeline_entries:
        return schemas.DayStats(
            total_events=0,
            total_duration_hours=0.0,
            top_project=None,
            active_time_hours=0.0,
            break_time_hours=0.0
        )
    
    # Calculate totals
    total_duration_seconds = sum(
        (entry.end_time - entry.start_time).total_seconds()
        for entry in timeline_entries
    )
    total_duration_hours = total_duration_seconds / 3600
    
    # Calculate project time distribution
    project_time: Dict[str, float] = {}
    for entry in timeline_entries:
        project_name = entry.project.name if entry.project else "Unassigned"
        duration_hours = (entry.end_time - entry.start_time).total_seconds() / 3600
        project_time[project_name] = project_time.get(project_name, 0) + duration_hours
    
    # Find top project
    top_project = max(project_time.items(), key=lambda x: x[1])[0] if project_time else None
    
    # For now, assume all timeline time is active time
    # In the future, you could implement logic to distinguish active vs break time
    active_time_hours = total_duration_hours
    break_time_hours = 0.0
    
    # Get event count for the day
    event_count_result = await db.execute(
        select(func.count(EventModel.id)).where(EventModel.local_day == target_date)
    )
    total_events = event_count_result.scalar() or 0
    
    return schemas.DayStats(
        total_events=total_events,
        total_duration_hours=total_duration_hours,
        top_project=top_project,
        active_time_hours=active_time_hours,
        break_time_hours=break_time_hours
    )

async def generate_daily_summary(target_date: date, stats: schemas.DayStats) -> schemas.DailySummary:
    """Generate a daily summary (placeholder implementation)"""
    # This is a placeholder - in the future you could use AI to generate insights
    summary_text = f"You were active for {stats.active_time_hours:.1f} hours"
    if stats.top_project:
        summary_text += f", primarily working on {stats.top_project}"
    
    insights = []
    if stats.total_duration_hours > 8:
        insights.append("High productivity day with extended active time")
    elif stats.total_duration_hours < 4:
        insights.append("Light activity day")
    
    if stats.top_project and stats.top_project != "Unassigned":
        insights.append(f"Focused primarily on {stats.top_project}")
    
    return schemas.DailySummary(
        date=target_date,
        summary=summary_text,
        insights=insights if insights else None
    )

@router.get("/{date_string}", response_model=schemas.DayDataResponse)
async def get_day_data(
    date_string: str = Path(..., regex=r"^\d{4}-\d{2}-\d{2}$", description="Date in YYYY-MM-DD format"),
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user)
):
    """Get timeline entries and summary for a specific day"""
    target_date = validate_date_string(date_string)
    
    # Get timeline entries
    timeline_entries = await get_timeline_entries_for_date(db, target_date)
    
    # Calculate statistics
    stats = await calculate_day_stats(db, target_date)
    
    # Generate summary
    summary = await generate_daily_summary(target_date, stats)
    
    return schemas.DayDataResponse(
        date=target_date,
        timeline_entries=[schemas.TimelineEntry.model_validate(entry) for entry in timeline_entries],
        stats=stats,
        summary=summary
    )

@router.get("/{date_string}/stats", response_model=schemas.DayStats)
async def get_day_stats(
    date_string: str = Path(..., regex=r"^\d{4}-\d{2}-\d{2}$", description="Date in YYYY-MM-DD format"),
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user)
):
    """Get statistics for a specific day"""
    target_date = validate_date_string(date_string)
    return await calculate_day_stats(db, target_date)

from typing import List, Optional, Dict, Any
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Path as FastAPIPath, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from central_server.api_service import schemas
from central_server.api_service.core.database import get_db
from central_server.api_service.core.models import TimelineEntry as TimelineEntryModel, Project as ProjectModel
from central_server.api_service.auth import get_current_active_user

router = APIRouter()

def parse_date_string(date_string: str) -> date:
    try:
        return date.fromisoformat(date_string)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Please use YYYY-MM-DD."
        )

async def get_timeline_entries_for_date(db: AsyncSession, target_date: date) -> List[schemas.TimelineEntry]:
    result = await db.execute(
        select(TimelineEntryModel)
        .options(selectinload(TimelineEntryModel.project))
        .where(TimelineEntryModel.local_day == target_date)
        .order_by(TimelineEntryModel.start_time)
    )
    entries = result.scalars().all()
    return [schemas.TimelineEntry.model_validate(entry) for entry in entries]

def calculate_day_stats(timeline_entries: List[schemas.TimelineEntry]) -> schemas.DayStats:
    total_events = len(timeline_entries)
    total_duration_hours = 0.0
    active_time_hours = 0.0
    break_time_hours = 0.0
    project_time_counts: Dict[str, float] = {}
    for entry in timeline_entries:
        duration_hours = (entry.end_time - entry.start_time).total_seconds() / 3600
        total_duration_hours += duration_hours
        active_time_hours += duration_hours
        if entry.project and entry.project.name:
            project_name = entry.project.name
            project_time_counts[project_name] = project_time_counts.get(project_name, 0) + duration_hours
    top_project = max(project_time_counts, key=lambda k: project_time_counts[k]) if project_time_counts else None
    return schemas.DayStats(
        total_events=total_events,
        total_duration_hours=total_duration_hours,
        top_project=top_project,
        active_time_hours=active_time_hours,
        break_time_hours=break_time_hours
    )

def create_placeholder_summary(target_date: date, stats: schemas.DayStats) -> schemas.DailySummary:
    return schemas.DailySummary(
        date=target_date,
        summary=f"Placeholder summary for {target_date.isoformat()}. Actual summary generation is pending.",
        insights=None
    )

@router.get("/{date_string}", response_model=schemas.DayDataResponse)
async def read_day_data(
    date_string: str = FastAPIPath(
        ..., 
        description="Date in YYYY-MM-DD format.", 
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user)
):
    target_date = parse_date_string(date_string)
    timeline_entries = await get_timeline_entries_for_date(db, target_date)
    stats = calculate_day_stats(timeline_entries)
    summary = create_placeholder_summary(target_date, stats)
    return schemas.DayDataResponse(
        date=target_date,
        timeline_entries=timeline_entries,
        stats=stats,
        summary=summary
    )
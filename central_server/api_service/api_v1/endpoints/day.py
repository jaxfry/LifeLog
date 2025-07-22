from typing import List, Optional, Dict, Any
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Path as FastAPIPath, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from central_server.api_service import schemas
from central_server.api_service.core.database import get_db
from central_server.api_service.core.models import TimelineEntry as TimelineEntryModel, Project as ProjectModel
from central_server.api_service.auth import require_auth
from central_server.processing_service.db_models import DailyReflectionOrm
from central_server.shared.utils import extract_summary_from_reflection
import asyncio
import re

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

@router.get("/{date_string}", response_model=schemas.DayDataResponse)
async def read_day_data(
    date_string: str = FastAPIPath(
        ..., 
        description="Date in YYYY-MM-DD format.", 
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth)
):
    target_date = parse_date_string(date_string)
    timeline_entries = await get_timeline_entries_for_date(db, target_date)
    stats = calculate_day_stats(timeline_entries)
    # Try to fetch the real LLM summary/reflection
    reflection_obj = await db.execute(
        select(DailyReflectionOrm).where(DailyReflectionOrm.local_day == target_date)
    )
    reflection = reflection_obj.scalar_one_or_none()
    if reflection:
        summary_text = str(reflection.summary) if not isinstance(reflection.summary, str) else reflection.summary
        insights = None  # Optionally parse more tags from reflection.reflection
    else:
        summary_text = f"LLM summary not available in API service for {target_date.isoformat()}."
        insights = None
    summary = schemas.DailySummary(
        date=target_date,
        summary=summary_text,
        insights=insights
    )
    return schemas.DayDataResponse(
        date=target_date,
        timeline_entries=timeline_entries,
        stats=stats,
        summary=summary
    )

@router.get("/{date_string}/solace_reflection", response_model=dict)
async def get_solace_daily_reflection(
    date_string: str = FastAPIPath(
        ..., 
        description="Date in YYYY-MM-DD format.", 
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth)
):
    # This endpoint cannot provide LLM reflection in this context
    return {"reflection": "LLM Solace reflection not available in API service."}
import uuid
import logging
from typing import List, Optional, Annotated
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app import schemas
from backend.app.core.db import get_db
from backend.app.api_v1.auth import get_current_active_user
from backend.app.models import TimelineEntry as TimelineEntryModel, Project as ProjectModel

router = APIRouter()
logger = logging.getLogger(__name__)

CurrentUserDep = Annotated[schemas.User, Depends(get_current_active_user)]
DBDep = Annotated[AsyncSession, Depends(get_db)]

# --- Async CRUD Operations for Timeline Entries ---
async def get_timeline_entries_db(
    db: AsyncSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    project_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 20,
    sort_by: str = "start_time",
    order: str = "desc"
) -> List[schemas.TimelineEntry]:
    query = select(TimelineEntryModel)
    if start_date:
        query = query.where(TimelineEntryModel.local_day >= start_date)
    if end_date:
        query = query.where(TimelineEntryModel.local_day <= end_date)
    if project_id:
        query = query.where(TimelineEntryModel.project_id == project_id)
    if sort_by in {"start_time", "end_time", "local_day"}:
        sort_col = getattr(TimelineEntryModel, sort_by)
        if order == "desc":
            sort_col = sort_col.desc()
        else:
            sort_col = sort_col.asc()
        query = query.order_by(sort_col)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    entries = result.scalars().all()
    timeline_entries = []
    for entry in entries:
        project_schema = None
        if entry.project:
            project_schema = schemas.Project(
                id=entry.project.id,
                name=entry.project.name
            )
        timeline_entries.append(
            schemas.TimelineEntry(
                id=entry.id,
                start_time=entry.start_time,
                end_time=entry.end_time,
                title=entry.title,
                summary=entry.summary,
                project_id=entry.project_id,
                local_day=entry.local_day,
                project=project_schema
            )
        )
    return timeline_entries

@router.get("", response_model=List[schemas.TimelineEntry])
async def read_timeline_entries(
    db: DBDep,
    current_user: CurrentUserDep,
    start_date: Optional[date] = Query(None, description="Filter by start date (YYYY-MM-DD). Inclusive."),
    end_date: Optional[date] = Query(None, description="Filter by end date (YYYY-MM-DD). Inclusive."),
    project_id: Optional[uuid.UUID] = Query(None, description="Filter by project ID."),
    skip: int = Query(0, ge=0, description="Number of items to skip."),
    limit: int = Query(20, ge=1, le=200, description="Number of items to return."),
    sort_by: str = Query("start_time", enum=["start_time", "end_time", "title", "local_day"], description="Field to sort by."),
    order: str = Query("desc", enum=["asc", "desc"], description="Sort order (asc or desc).")
):
    """
    Retrieve timeline entries with filtering, sorting, and pagination.
    """
    return await get_timeline_entries_db(db, start_date, end_date, project_id, skip, limit, sort_by, order)

@router.get("/{entry_id}", response_model=schemas.TimelineEntry)
async def read_timeline_entry(
    entry_id: uuid.UUID,
    db: DBDep,
    current_user: CurrentUserDep
):
    """
    Get a specific timeline entry by its ID.
    """
    query = select(TimelineEntryModel).where(TimelineEntryModel.id == entry_id)
    result = await db.execute(query)
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Timeline entry not found")
    project_schema = None
    if entry.project:
        project_schema = schemas.Project(id=entry.project.id, name=entry.project.name)
    return schemas.TimelineEntry(
        id=entry.id,
        start_time=entry.start_time,
        end_time=entry.end_time,
        title=entry.title,
        summary=entry.summary,
        project_id=entry.project_id,
        local_day=entry.local_day,
        project=project_schema
    )
# ...existing code for create/update/delete can be migrated to async as needed...
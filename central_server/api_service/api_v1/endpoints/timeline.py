from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from datetime import date
import uuid

from central_server.api_service.core.database import get_db
from central_server.api_service.core.models import TimelineEntry as TimelineEntryModel, Project as ProjectModel
from central_server.api_service.auth import require_auth
from central_server.api_service import schemas

router = APIRouter()

async def get_timeline_entry_by_id(db: AsyncSession, entry_id: uuid.UUID) -> TimelineEntryModel:
    result = await db.execute(
        select(TimelineEntryModel)
        .options(selectinload(TimelineEntryModel.project))
        .where(TimelineEntryModel.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Timeline entry not found"
        )
    return entry

@router.post("", response_model=schemas.TimelineEntry, status_code=status.HTTP_201_CREATED)
async def create_timeline_entry(
    entry_in: schemas.TimelineEntryCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth)
):
    if entry_in.project_id:
        result = await db.execute(select(ProjectModel).where(ProjectModel.id == entry_in.project_id))
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
    db_entry = TimelineEntryModel(
        start_time=entry_in.start_time,
        end_time=entry_in.end_time,
        title=entry_in.title,
        summary=entry_in.summary,
        project_id=entry_in.project_id,
        local_day=entry_in.start_time.date()
    )
    db.add(db_entry)
    await db.commit()
    await db.refresh(db_entry)
    entry_with_project = await get_timeline_entry_by_id(db, db_entry.id)
    return schemas.TimelineEntry.model_validate(entry_with_project)

@router.get("", response_model=list[schemas.TimelineEntry])
async def get_timeline_entries(
    start_date: date | None = Query(None, description="Filter by start date (inclusive)"),
    end_date: date | None = Query(None, description="Filter by end date (inclusive)"),
    project_id: uuid.UUID | None = Query(None, description="Filter by project ID"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of items to return"),
    sort_by: str = Query("start_time", regex="^(start_time|end_time|title|local_day)$", description="Sort field"),
    order: str = Query("desc", regex="^(asc|desc)$", description="Sort order"),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth)
):
    query = select(TimelineEntryModel).options(selectinload(TimelineEntryModel.project))
    conditions = []
    if start_date:
        conditions.append(TimelineEntryModel.local_day >= start_date)
    if end_date:
        conditions.append(TimelineEntryModel.local_day <= end_date)
    if project_id:
        conditions.append(TimelineEntryModel.project_id == project_id)
    if conditions:
        query = query.where(and_(*conditions))
    sort_column = getattr(TimelineEntryModel, sort_by)
    if order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    entries = result.scalars().all()
    return [schemas.TimelineEntry.model_validate(entry) for entry in entries]

@router.get("/{entry_id}", response_model=schemas.TimelineEntry)
async def get_timeline_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth)
):
    entry = await get_timeline_entry_by_id(db, entry_id)
    return schemas.TimelineEntry.model_validate(entry)

@router.put("/{entry_id}", response_model=schemas.TimelineEntry)
async def update_timeline_entry(
    entry_id: uuid.UUID,
    entry_update: schemas.TimelineEntryUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth)
):
    entry = await get_timeline_entry_by_id(db, entry_id)
    if entry_update.project_id:
        result = await db.execute(select(ProjectModel).where(ProjectModel.id == entry_update.project_id))
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
    if entry_update.start_time is not None:
        entry.start_time = entry_update.start_time
        entry.local_day = entry_update.start_time.date()
    if entry_update.end_time is not None:
        entry.end_time = entry_update.end_time
    if entry_update.title is not None:
        entry.title = entry_update.title
    if entry_update.summary is not None:
        entry.summary = entry_update.summary
    if entry_update.project_id is not None:
        entry.project_id = entry_update.project_id
    await db.commit()
    await db.refresh(entry)
    entry_with_project = await get_timeline_entry_by_id(db, entry.id)
    return schemas.TimelineEntry.model_validate(entry_with_project)

@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_timeline_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth)
):
    entry = await get_timeline_entry_by_id(db, entry_id)
    await db.delete(entry)
    await db.commit()
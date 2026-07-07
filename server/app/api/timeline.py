from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_session
from app.core.dependencies import get_current_user, Pagination
from app.models.auth import User
from app.models.processing import Session, TimelineEntry

router = APIRouter()


@router.get("/timeline")
async def list_timeline_entries(
    logical_date: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    pagination: Pagination = Depends(),
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_session),
):
    statement = select(TimelineEntry)

    if logical_date:
        statement = statement.where(TimelineEntry.logical_date == logical_date)
    if session_id:
        statement = statement.where(TimelineEntry.session_id == session_id)
    if category:
        statement = statement.where(TimelineEntry.category == category)

    statement = (
        statement
        .order_by(TimelineEntry.start_time.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )

    result = await db_session.execute(statement)
    entries = result.scalars().all()
    return entries


@router.get("/timeline/{entry_id}")
async def get_timeline_entry(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_session),
):
    entry = await db_session.get(TimelineEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Timeline entry not found")
    return entry


@router.get("/timeline/by-session/{session_id}")
async def get_timeline_entries_by_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_session),
):
    session_obj = await db_session.get(Session, session_id)
    if not session_obj:
        raise HTTPException(status_code=404, detail="Session not found")

    statement = (
        select(TimelineEntry)
        .where(TimelineEntry.session_id == session_id)
        .order_by(TimelineEntry.start_time.asc())
    )
    result = await db_session.execute(statement)
    entries = result.scalars().all()
    return entries

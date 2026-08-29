from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, or_, select

from app.core.database import get_session
from app.core.dependencies import Pagination, get_current_user
from app.models.auth import User
from app.models.processing import Session, TimelineEntry

router = APIRouter()


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


@router.get("/timeline")
async def list_timeline_entries(
    logical_date: str | None = Query(None),
    session_id: str | None = Query(None),
    category: str | None = Query(None),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    q: str | None = None,
    pagination: Pagination = Depends(),
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_session),
):
    start_date = _normalize_dt(start_date)
    end_date = _normalize_dt(end_date)

    statement = select(TimelineEntry).where(
        TimelineEntry.owner_user_id == current_user.id
    )

    if logical_date:
        statement = statement.where(TimelineEntry.logical_date == logical_date)
    if session_id:
        statement = statement.where(TimelineEntry.session_id == session_id)
    if category:
        statement = statement.where(TimelineEntry.category == category)
    if start_date:
        statement = statement.where(TimelineEntry.start_time >= start_date)
    if end_date:
        statement = statement.where(TimelineEntry.end_time <= end_date)
    if q:
        statement = statement.where(
            or_(
                col(TimelineEntry.activity).ilike(f"%{q}%"),
                col(TimelineEntry.notes).ilike(f"%{q}%"),
                col(TimelineEntry.category).ilike(f"%{q}%"),
            )
        )

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
    entry = (
        await db_session.execute(
            select(TimelineEntry).where(
                TimelineEntry.id == entry_id,
                TimelineEntry.owner_user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Timeline entry not found")
    return entry


@router.get("/timeline/by-session/{session_id}")
async def get_timeline_entries_by_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_session),
):
    session_obj = (
        await db_session.execute(
            select(Session).where(
                Session.id == session_id,
                Session.owner_user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
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

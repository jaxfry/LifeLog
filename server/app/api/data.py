from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.core.database import get_session
from app.core.dependencies import Pagination
from app.models.ingest import Event, RawLog
from app.models.processing import Session

router = APIRouter()


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


@router.get("/sessions")
async def get_sessions(
    pagination: Pagination = Depends(),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    status: str | None = None,
    db_session: AsyncSession = Depends(get_session),
):
    start_date = _normalize_dt(start_date)
    end_date = _normalize_dt(end_date)

    stmt = select(Session).order_by(col(Session.start_time).desc())

    if start_date:
        stmt = stmt.where(Session.start_time >= start_date)
    if end_date:
        stmt = stmt.where(Session.end_time <= end_date)
    if status:
        stmt = stmt.where(Session.status == status)

    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db_session.execute(stmt)
    return result.scalars().all()


@router.get("/logs")
async def get_logs(
    pagination: Pagination = Depends(),
    extension_id: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db_session: AsyncSession = Depends(get_session),
):
    start_date = _normalize_dt(start_date)
    end_date = _normalize_dt(end_date)

    stmt = select(RawLog).order_by(col(RawLog.received_at).desc())

    if extension_id:
        stmt = stmt.where(RawLog.extension_id == extension_id)
    if start_date:
        stmt = stmt.where(RawLog.received_at >= start_date)
    if end_date:
        stmt = stmt.where(RawLog.received_at <= end_date)

    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db_session.execute(stmt)
    return result.scalars().all()


@router.get("/events")
async def get_events(
    pagination: Pagination = Depends(),
    extension_id: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db_session: AsyncSession = Depends(get_session),
):
    start_date = _normalize_dt(start_date)
    end_date = _normalize_dt(end_date)

    if extension_id:
        stmt = (
            select(Event)
            .join(RawLog)
            .where(RawLog.extension_id == extension_id)
        )
    else:
        stmt = select(Event)

    stmt = stmt.where(Event.is_superseded == False)
    stmt = stmt.order_by(col(Event.created_at).desc())

    if start_date:
        stmt = stmt.where(Event.created_at >= start_date)
    if end_date:
        stmt = stmt.where(Event.created_at <= end_date)

    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db_session.execute(stmt)
    return result.scalars().all()

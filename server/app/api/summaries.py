
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.core.database import get_session
from app.core.dependencies import Pagination, get_current_user
from app.models.auth import User
from app.models.processing import DailySummary

router = APIRouter()


@router.get("/chapters")
async def list_chapters(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    q: str | None = Query(None),
    pagination: Pagination = Depends(),
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_session),
):
    """Return daily summaries in the timeline's chapter display shape.

    Chapters are a presentation projection over durable daily summaries; they
    are not a separate source of truth or table.
    """
    statement = select(DailySummary).where(
        DailySummary.owner_user_id == current_user.id
    )
    if start_date:
        statement = statement.where(DailySummary.logical_date >= start_date[:10])
    if end_date:
        statement = statement.where(DailySummary.logical_date <= end_date[:10])
    if q:
        statement = statement.where(
            or_(
                col(DailySummary.logical_date).ilike(f"%{q}%"),
                col(DailySummary.summary_text).ilike(f"%{q}%"),
            )
        )
    statement = (
        statement.order_by(DailySummary.logical_date.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    result = await db_session.execute(statement)
    summaries = result.scalars().all()
    return [
        {
            "id": summary.logical_date,
            "title": summary.logical_date,
            "summary": summary.summary_text,
            "start_time": f"{summary.logical_date}T00:00:00",
            "end_time": f"{summary.logical_date}T23:59:59",
            "timezone": "UTC",
        }
        for summary in summaries
    ]


@router.get("/summaries/{logical_date}")
async def get_daily_summary(
    logical_date: str,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_session),
):
    summary = (
        await db_session.execute(
            select(DailySummary).where(
                DailySummary.owner_user_id == current_user.id,
                DailySummary.logical_date == logical_date,
            )
        )
    ).scalar_one_or_none()
    if not summary:
        raise HTTPException(status_code=404, detail="Daily summary not found")
    return summary


@router.get("/summaries")
async def list_daily_summaries(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    pagination: Pagination = Depends(),
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_session),
):
    statement = select(DailySummary).where(
        DailySummary.owner_user_id == current_user.id
    )

    if start_date:
        statement = statement.where(DailySummary.logical_date >= start_date)
    if end_date:
        statement = statement.where(DailySummary.logical_date <= end_date)

    statement = (
        statement.order_by(DailySummary.logical_date.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    result = await db_session.execute(statement)
    summaries = result.scalars().all()
    return summaries

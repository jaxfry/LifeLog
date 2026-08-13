
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_session
from app.core.dependencies import Pagination, get_current_user
from app.models.auth import User
from app.models.processing import DailySummary

router = APIRouter()


@router.get("/summaries/{logical_date}")
async def get_daily_summary(
    logical_date: str,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_session),
):
    summary = await db_session.get(DailySummary, logical_date)
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
    statement = select(DailySummary)

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

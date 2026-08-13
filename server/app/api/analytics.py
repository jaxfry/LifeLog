from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_session
from app.models.auth import Device
from app.models.config import Extension
from app.models.ingest import Event, RawLog
from app.models.processing import Session, TimelineEntry

router = APIRouter()

# Portable per-day truncation that works on both PostgreSQL and SQLite
_DAY_COL = func.date(Session.start_time)


@router.get("/stats")
async def get_stats(db_session: AsyncSession = Depends(get_session)):
    total_sessions = (await db_session.execute(select(func.count()).select_from(Session))).scalar_one()
    total_events = (await db_session.execute(select(func.count()).select_from(Event))).scalar_one()

    min_date = (await db_session.execute(select(func.min(Session.start_time)))).scalar_one()
    max_date = (await db_session.execute(select(func.max(Session.start_time)))).scalar_one()

    avg_sessions_per_day = 0
    if min_date and max_date:
        days = (max_date - min_date).days + 1
        if days > 0:
            avg_sessions_per_day = round(total_sessions / days, 1)

    return {
        "total_sessions": total_sessions,
        "total_events": total_events,
        "avg_sessions_per_day": avg_sessions_per_day,
        "first_activity_date": min_date,
        "last_activity_date": max_date,
    }


@router.get("/activity-volume")
async def get_activity_volume(
    days: int = Query(7, ge=1, le=365),
    db_session: AsyncSession = Depends(get_session),
):
    end_date = datetime.now(UTC).replace(tzinfo=None)
    start_date = end_date - timedelta(days=days)

    query = (
        select(
            _DAY_COL.label("date"),
            func.count(Session.id).label("count"),
        )
        .where(Session.start_time >= start_date)
        .group_by(_DAY_COL)
        .order_by(_DAY_COL)
    )

    result = await db_session.execute(query)
    rows = result.all()

    data = {str(row.date)[:10]: row.count for row in rows}
    filled = []
    current = start_date
    while current <= end_date:
        ds = current.strftime("%Y-%m-%d")
        filled.append({"date": ds, "count": data.get(ds, 0)})
        current += timedelta(days=1)

    return filled


@router.get("/status-distribution")
async def get_status_distribution(db_session: AsyncSession = Depends(get_session)):
    query = select(Session.status, func.count()).group_by(Session.status)
    result = await db_session.execute(query)
    return [{"name": row[0], "value": row[1]} for row in result.all()]


@router.get("/dashboard-metrics")
async def get_dashboard_metrics(db_session: AsyncSession = Depends(get_session)):
    total_events = (
        await db_session.execute(
            select(func.count()).select_from(Event).where(Event.is_superseded == False)
        )
    ).scalar_one()

    active_collectors = (
        await db_session.execute(
            select(func.count()).select_from(Extension).where(Extension.is_active == True)
        )
    ).scalar_one()

    ai_processing = (
        await db_session.execute(select(func.count()).select_from(TimelineEntry))
    ).scalar_one()

    end_date = datetime.now(UTC).replace(tzinfo=None)
    start_date = end_date - timedelta(days=7)

    query = (
        select(
            _DAY_COL.label("date"),
            func.count(Session.id).label("count"),
        )
        .where(Session.start_time >= start_date)
        .group_by(_DAY_COL)
        .order_by(_DAY_COL)
    )
    result = await db_session.execute(query)
    rows = result.all()

    activity_volume = []
    current = start_date
    data = {str(row.date)[:10]: row.count for row in rows}
    while current <= end_date:
        ds = current.strftime("%Y-%m-%d")
        activity_volume.append({"date": ds, "count": data.get(ds, 0)})
        current += timedelta(days=1)

    return {
        "total_events": total_events,
        "active_collectors": active_collectors,
        "ai_processing": ai_processing,
        "activity_volume": activity_volume,
    }


@router.get("/collector-stats")
async def get_collector_stats(db_session: AsyncSession = Depends(get_session)):
    devices_result = await db_session.execute(select(Device))
    devices = devices_result.scalars().all()

    stats = []
    for device in devices:
        recent_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
        recent_logs = (
            await db_session.execute(
                select(func.count()).select_from(RawLog).where(
                    RawLog.device_id == device.id,
                    RawLog.received_at >= recent_cutoff,
                )
            )
        ).scalar_one()

        ext_count = (
            await db_session.execute(
                select(func.count(func.distinct(RawLog.extension_id)))
                .select_from(RawLog)
                .where(RawLog.device_id == device.id)
            )
        ).scalar_one()

        stats.append({
            "device_id": device.id,
            "device_name": device.name,
            "device_type": device.device_type,
            "collectors_count": ext_count,
            "recent_activity": recent_logs > 0,
            "last_cursor": device.last_cursor,
        })

    return stats

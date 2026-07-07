from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col

from app.core.config import settings
from app.core.logger import get_logger
from app.models.ingest import Event
from app.models.processing import Session

logger = get_logger(__name__)


def _logical_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


async def run_sessionizer(session: AsyncSession) -> int:
    """
    Find un-sessioned events and group them into sessions.
    Returns the number of sessions created.
    """
    statement = (
        select(Event)
        .where(Event.is_superseded == False)
        .where(Event.session_id.is_(None))
        .order_by(Event.start_time.asc())
    )
    result = await session.execute(statement)
    events = result.scalars().all()

    if not events:
        return 0

    groups = _group_into_sessions(events)

    sessions_created = 0
    for group in groups:
        start_time = min(e.start_time for e in group)
        end_time = max((e.end_time or e.start_time) for e in group)

        ses = Session(
            start_time=start_time,
            end_time=end_time,
            status="pending",
            logical_date=_logical_date(start_time),
        )
        session.add(ses)
        await session.flush()

        for evt in group:
            evt.session_id = ses.id
            evt.logical_date = evt.logical_date or _logical_date(evt.start_time)
            session.add(evt)

        sessions_created += 1

    await session.commit()
    logger.info(
        "Sessionizer: %d events -> %d sessions", len(events), sessions_created
    )
    return sessions_created


def _group_into_sessions(events: List[Event]) -> List[List[Event]]:
    gap_minutes = settings.SESSION_GAP_MINUTES
    groups: List[List[Event]] = []
    current: List[Event] = []

    for evt in events:
        if not current:
            current.append(evt)
            continue

        prev_end = current[-1].end_time or current[-1].start_time
        curr_start = evt.start_time

        gap = (curr_start - prev_end).total_seconds() / 60

        if gap > gap_minutes or _crosses_logical_date(prev_end, curr_start):
            groups.append(current)
            current = [evt]
        else:
            current.append(evt)

    if current:
        groups.append(current)

    return groups


def _crosses_logical_date(a: datetime, b: datetime) -> bool:
    return _logical_date(a) != _logical_date(b)

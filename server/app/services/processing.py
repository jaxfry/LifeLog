from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logger import get_logger
from app.models.ingest import Event
from app.models.processing import Session
from app.services.sessionizer import run_sessionizer

logger = get_logger(__name__)


async def run_processing_pipeline(session: AsyncSession) -> dict:
    """
    Orchestrate the full processing pipeline:
    1. Sessionize un-grouped events
    2. Mark dirty sessions for reprocessing
    """
    result = {
        "sessions_created": 0,
        "sessions_marked_dirty": 0,
    }

    result["sessions_created"] = await run_sessionizer(session)

    result["sessions_marked_dirty"] = await _mark_dirty_sessions(session)

    if result["sessions_created"] or result["sessions_marked_dirty"]:
        await session.commit()

    return result


async def _mark_dirty_sessions(session: AsyncSession) -> int:
    """
    If any events have been superseded, mark their sessions as needing
    reprocessing (status = pending).
    """
    statement = (
        select(Session)
        .where(Session.status.in_(["completed", "failed"]))
        .where(
            select(Event)
            .where(Event.session_id == Session.id)
            .where(Event.is_superseded == True)
            .exists()
        )
    )
    result = await session.execute(statement)
    dirty_sessions = result.scalars().all()

    for ses in dirty_sessions:
        ses.status = "pending"
        ses.processing_status = "ready"
        ses.retry_count = 0
        session.add(ses)

    return len(dirty_sessions)


async def get_sessions_ready_for_ai(
    session: AsyncSession, limit: int = 10
) -> list[Session]:
    """
    Fetch sessions that are ready for AI enrichment.
    """
    statement = (
        select(Session)
        .where(Session.status == "pending")
        .where(Session.processing_status == "ready")
        .order_by(Session.start_time.asc())
        .limit(limit)
    )
    result = await session.execute(statement)
    return list(result.scalars().all())

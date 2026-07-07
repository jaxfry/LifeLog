from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.logger import get_logger
from app.models.ingest import Event
from app.models.processing import Session, TimelineEntry
from app.services.ai import call_llm, count_tokens
from app.services.cache import _cache_key
from app.services.prompts import get_prompt, render_prompt
from app.services.processing import get_sessions_ready_for_ai

logger = get_logger(__name__)


async def generate_timeline_for_session(
    db_session: AsyncSession,
    session_obj: Session,
) -> Optional[TimelineEntry]:
    if session_obj.status != "pending":
        return None

    events_stmt = (
        select(Event)
        .where(Event.session_id == session_obj.id)
        .where(Event.is_superseded == False)
        .order_by(Event.start_time.asc())
    )
    result = await db_session.execute(events_stmt)
    events = result.scalars().all()

    if not events:
        session_obj.status = "completed"
        session_obj.processing_status = "completed"
        db_session.add(session_obj)
        await db_session.commit()
        return None

    events_text = _format_events(events)
    template = await get_prompt(db_session, "timeline_generation")
    if not template:
        logger.error("No timeline_generation prompt found")
        return None

    user_prompt = render_prompt(template, events=events_text)

    cache_data = {
        "session_id": str(session_obj.id),
        "events_hash": hash(events_text),
    }
    cache_key = _cache_key("timeline", cache_data)

    try:
        content = await call_llm(
            db_session=db_session,
            system_prompt="You are a personal timeline generator. Be concise and factual.",
            user_prompt=user_prompt,
            cache_key=cache_key,
        )
    except RuntimeError:
        logger.error("Failed to generate timeline for session %s", session_obj.id)
        session_obj.status = "failed"
        session_obj.processing_status = "failed"
        session_obj.retry_count += 1
        db_session.add(session_obj)
        await db_session.commit()
        return None

    entry = TimelineEntry(
        session_id=session_obj.id,
        start_time=session_obj.start_time,
        end_time=session_obj.end_time,
        activity=content.strip(),
        logical_date=session_obj.logical_date,
    )
    db_session.add(entry)
    await db_session.flush()

    session_obj.status = "completed"
    session_obj.processing_status = "completed"
    db_session.add(session_obj)
    await db_session.commit()

    logger.info(
        "Generated timeline entry %s for session %s",
        entry.id,
        session_obj.id,
    )
    return entry


async def process_pending_sessions(
    db_session: AsyncSession,
    limit: int = 10,
) -> int:
    sessions = await get_sessions_ready_for_ai(db_session, limit=limit)
    processed = 0
    for ses in sessions:
        try:
            result = await generate_timeline_for_session(db_session, ses)
            if result:
                processed += 1
        except Exception:
            logger.exception("Failed to process session %s", ses.id)
            ses.status = "failed"
            ses.processing_status = "failed"
            ses.retry_count += 1
            db_session.add(ses)
            await db_session.commit()
    return processed


def _format_events(events: list[Event]) -> str:
    lines = []
    for e in events:
        start = e.start_time.strftime("%H:%M")
        end = e.end_time.strftime("%H:%M") if e.end_time else "?"
        data_summary = _summarize_event_data(e.data)
        lines.append(f"  [{start}-{end}] {e.event_type}: {data_summary}")
    return "\n".join(lines)


def _summarize_event_data(data: dict) -> str:
    if not data:
        return ""
    title = data.get("title") or data.get("name") or data.get("app") or data.get("url") or ""
    if isinstance(title, str) and title:
        return title
    return str(data)[:120]

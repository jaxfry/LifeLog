from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logger import get_logger
from app.core.utils.time import get_logical_date
from app.loader.runner import run_normalization
from app.models.ingest import Event, RawLog
from app.services.extraction import extract_event_facts
from app.services.failures import record_processing_failure
from app.services.retrieval import upsert_search_document

logger = get_logger(__name__)


async def process_log(session: AsyncSession, log_id: UUID) -> list[Event]:
    """
    Loads a RawLog, runs the extension processor, and saves Events.
    """
    log = await session.get(RawLog, log_id)
    if not log:
        logger.error("Log %s not found", log_id)
        return []

    if log.processing_status == "done":
        existing_events = (
            await session.execute(
                select(Event)
                .where(Event.source_log_id == log.id)
                .where(Event.is_superseded == False)
            )
        ).scalars().all()
        for event in existing_events:
            await extract_event_facts(session, event)
        await session.commit()
        return list(existing_events)

    logger.info("Processing log %s with extension %s", log_id, log.extension_id)

    try:
        events_data = run_normalization(log.extension_id, log.payload)
        created_events = []
        for event_data in events_data:
            data = event_data.get("data", {})
            start_time_iso = data.get("timestamp") or data.get("start_time")
            event_dt = _parse_event_time(start_time_iso, log.received_at)
            event = Event(
                source_log_id=log.id,
                event_type=event_data.get("type", "unknown"),
                start_time=event_dt,
                data=data,
                logical_date=get_logical_date(event_dt, "UTC"),
                processing_version=1,
                confidence=1.0 if start_time_iso else 0.7,
            )
            session.add(event)
            created_events.append(event)

        await session.flush()
        for event in created_events:
            await extract_event_facts(session, event)
            await upsert_search_document(
                session,
                source_type="event",
                source_id=event.id,
                title=event.event_type,
                content=f"{event.event_type}\n{event.data}",
                occurred_at=event.start_time,
                logical_date=event.logical_date,
                metadata={"extension_id": log.extension_id, "event_type": event.event_type},
            )

        log.processing_status = "done"
        session.add(log)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        failed_log = await session.get(RawLog, log_id)
        if failed_log is not None:
            failed_log.processing_status = "failed"
            session.add(failed_log)
            await record_processing_failure(
                session,
                source_type="raw_log",
                source_id=log_id,
                stage="normalization",
                error=exc,
                context={"extension_id": failed_log.extension_id},
            )
            await session.commit()
        logger.exception("Normalization or memory extraction failed for log %s", log_id)
        raise

    logger.info("Created %d events and extracted their memory facts", len(created_events))
    return created_events


def _parse_event_time(value: object, fallback: datetime) -> datetime:
    if value is None:
        return fallback.replace(tzinfo=None)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return fallback.replace(tzinfo=None)
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed

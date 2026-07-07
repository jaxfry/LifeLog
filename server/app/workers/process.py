from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import async_session_factory
from app.core.logger import get_logger
from app.models.ingest import Event, RawLog

logger = get_logger(__name__)


async def process_raw_log(ctx: dict, raw_log_id: str) -> bool:
    """
    ARQ worker task: normalize a RawLog into Events.

    For now this extracts simple events from the payload. Extensions can
    provide custom normalization logic later.
    """
    async with async_session_factory() as session:
        raw_log = await session.get(RawLog, raw_log_id)
        if not raw_log:
            logger.warning("RawLog %s not found, skipping", raw_log_id)
            return False

        try:
            payload = raw_log.payload
            if not isinstance(payload, dict):
                payload = {}

            events_data = payload.get("events", [payload])
            if isinstance(events_data, dict):
                events_data = [events_data]

            for evt in events_data:
                event = Event(
                    source_log_id=raw_log.id,
                    event_type=evt.get("type", "unknown"),
                    start_time=_parse_dt(evt.get("start_time")) or raw_log.received_at,
                    end_time=_parse_dt(evt.get("end_time")),
                    data=evt,
                    logical_date=raw_log.logical_date,
                )
                session.add(event)

            raw_log.processing_status = "done"
            session.add(raw_log)
            await session.commit()
            logger.info(
                "Processed RawLog %s -> %d events",
                raw_log_id,
                len(events_data),
            )
            return True

        except Exception:
            raw_log.processing_status = "failed"
            session.add(raw_log)
            await session.commit()
            logger.exception("Failed to process RawLog %s", raw_log_id)
            return False


async def enqueue_process_raw_log(arq_pool, raw_log_id: str):
    """Enqueue a raw_log for processing by the ARQ worker."""
    await arq_pool.enqueue_job("process_raw_log", raw_log_id)


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            return None
    return None

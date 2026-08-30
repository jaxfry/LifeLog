"""
ActivityWatch Connector extension for LifeLog

Registers source and processor actors that convert AW window events into LifeLog events.
"""

import logging
from typing import Any, Optional
from datetime import datetime, timedelta, timezone

from lifelog.core.actors import ActorBase, ActorConfig, actor_registry
from lifelog import models
from lifelog.db import async_session
from sqlmodel import select

logger = logging.getLogger(__name__)


@actor_registry.register(
    ActorConfig(
        slug="activitywatch-source",
        actor_type=models.ActorType.SOURCE,
        version="1.0.0",
    )
)
class ActivityWatchSource(ActorBase):
    """Source actor placeholder for ActivityWatch data ingestion."""

    async def run(self, data: Any) -> Any:
        # Source actors are typically passive - they're referenced by client collectors.
        # The actual ingestion happens via /ingest endpoint with source_actor_slug="activitywatch-source"
        logger.debug("ActivityWatch source actor invoked (placeholder)")
        return data


@actor_registry.register(
    ActorConfig(
        slug="aw-processor",
        actor_type=models.ActorType.PROCESSOR,
        version="1.0.0",
    )
)
class ActivityWatchProcessor(ActorBase):
    """Processor that reads raw ActivityWatch events and emits computer-activity events."""

    async def run(self, data: models.RawLog) -> Any:
        raw_log = data
        if not raw_log or not isinstance(raw_log.raw_data, dict):
            logger.warning("AW processor received invalid raw_data")
            return

        payload = raw_log.raw_data
        events = payload.get("events") or []
        bucket = payload.get("bucket") or "unknown"

        if not events:
            logger.info("AW processor: no events in raw_log %s", raw_log.id)
            return

        async with async_session() as session:
            # Resolve our own actor id (processor)
            actor_stmt = select(models.Actor).where(models.Actor.slug == "aw-processor").order_by(models.Actor.id.desc()).limit(1)
            actor = (await session.exec(actor_stmt)).first()
            if not actor or actor.id is None:
                logger.error("AW processor actor not found in DB")
                return

            # Resolve event type id for computer-activity
            et_stmt = select(models.EventType).where(models.EventType.slug == "computer-activity").order_by(models.EventType.id.desc()).limit(1)
            et = (await session.exec(et_stmt)).first()
            if not et or et.id is None:
                logger.error("EventType 'computer-activity' not found; ensure manifest was installed")
                return

            created = 0
            for ev in events:
                try:
                    # AW event structure typically: {"timestamp": iso, "duration": seconds, "data": {"app": ..., "title": ...}}
                    ts = ev.get("timestamp") or ev.get("start")
                    dur = ev.get("duration")
                    data_obj = ev.get("data") or {}
                    app = data_obj.get("app") or data_obj.get("application") or ""
                    title = data_obj.get("title") or data_obj.get("window") or ""

                    start_dt = _parse_iso(ts)
                    end_dt: Optional[datetime] = None
                    if isinstance(dur, (int, float)):
                        end_dt = start_dt + timedelta(seconds=float(dur))

                    summary = f"{app} - {title}".strip(" -")

                    event = models.Event(
                        processor_actor_id=actor.id,
                        start_time=start_dt,
                        end_time=end_dt,
                        event_type_id=et.id,
                        summary=summary,
                    )
                    # Link to raw_log via relationship
                    event.raw_logs = [raw_log]
                    session.add(event)
                    await session.flush()
                    created += 1
                except Exception as e:
                    logger.warning("AW processor: failed to create event from %s: %s", ev, e)
            await session.commit()
            logger.info("AW processor created %s events from bucket=%s raw_log_id=%s", created, bucket, raw_log.id)


def _parse_iso(s: str) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    # Normalize Z suffix to +00:00
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        # Fallback to now
        return datetime.now(timezone.utc)

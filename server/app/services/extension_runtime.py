from datetime import datetime

from apscheduler.triggers.cron import CronTrigger
from sqlmodel import select

from app.core.database import async_session_factory
from app.core.logger import get_logger
from app.loader.contracts import ExtensionManifest
from app.loader.runner import run_poller
from app.models.config import Extension
from app.services.failures import record_processing_failure
from app.services.ingestion import ingest_log
from app.workers.process import process_log

logger = get_logger(__name__)


async def poll_extension(extension_id: str) -> dict[str, int]:
    """Acquire via adapter, then hand each envelope to the normal base pipeline."""
    async with async_session_factory() as session:
        extension = await session.get(Extension, extension_id)
        if extension is None or not extension.is_active:
            return {"received": 0, "created": 0}
        manifest = ExtensionManifest.model_validate(extension.config)
        if "collector" not in manifest.capabilities:
            raise ValueError(f"extension {extension_id} is scheduled but lacks collector capability")
        try:
            envelopes = await run_poller(extension_id, extension.config)
            created_ids = []
            for envelope in envelopes:
                payload = envelope.get("payload", envelope)
                timestamp = envelope.get("client_timestamp")
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                log, created = await ingest_log(
                    session,
                    device_id=f"poller:{extension_id}",
                    extension_id=extension_id,
                    payload=payload,
                    client_timestamp=timestamp,
                    client_timezone=envelope.get("client_timezone"),
                )
                if created:
                    created_ids.append(log.id)
            for log_id in created_ids:
                await process_log(session, log_id)
            return {"received": len(envelopes), "created": len(created_ids)}
        except Exception as exc:
            await session.rollback()
            await record_processing_failure(
                session,
                source_type="extension",
                source_id=None,
                stage="poller",
                error=exc,
                context={"extension_id": extension_id},
            )
            await session.commit()
            logger.exception("Extension poller failed for %s", extension_id)
            raise


async def configure_extension_pollers(scheduler) -> int:
    """Translate active manifest schedules into stable APScheduler jobs."""
    async with async_session_factory() as session:
        extensions = (
            await session.execute(
                select(Extension).where(Extension.is_active == True, Extension.scheduler_cron.is_not(None))
            )
        ).scalars().all()
    count = 0
    for extension in extensions:
        manifest = ExtensionManifest.model_validate(extension.config)
        if "collector" not in manifest.capabilities or not extension.scheduler_cron:
            continue
        scheduler.add_job(
            poll_extension,
            CronTrigger.from_crontab(extension.scheduler_cron),
            args=[extension.id],
            id=f"extension-poller:{extension.id}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        count += 1
    return count

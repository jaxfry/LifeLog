import uuid
from datetime import UTC, datetime, timedelta

from apscheduler.jobstores.base import JobLookupError
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import select

from app.core.database import async_session_factory
from app.core.logger import get_logger
from app.loader.contracts import ExtensionManifest
from app.loader.runner import run_poller
from app.models.config import Extension
from app.models.sources import SourceCheckpoint, SourceConnection
from app.services.context import copy_context
from app.services.failures import record_processing_failure
from app.services.ingestion import ingest_log
from app.services.source_secrets import get_source_secrets
from app.workers.process import process_log

logger = get_logger(__name__)
MAX_PAGES_PER_RUN = 20


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _redact_error(error: Exception, secrets: dict[str, str]) -> RuntimeError:
    message = f"{type(error).__name__}: {error}"
    for value in secrets.values():
        if value:
            message = message.replace(value, "[REDACTED]")
    return RuntimeError(message[:2000])


async def enqueue_source_poll(arq_pool, connection_id: uuid.UUID) -> None:
    """Scheduler entry point: queue acquisition; never execute adapters in the API process."""
    if arq_pool is None:
        logger.warning("Skipping scheduled source %s: worker queue unavailable", connection_id)
        return
    await arq_pool.enqueue_job(
        "task_poll_source",
        str(connection_id),
        _job_id=f"source-poll:{connection_id}",
    )


async def enqueue_legacy_extension_poll(arq_pool, extension_id: str) -> None:
    if arq_pool is None:
        logger.warning("Skipping scheduled legacy extension %s: worker queue unavailable", extension_id)
        return
    await arq_pool.enqueue_job(
        "task_poll_extension",
        extension_id,
        _job_id=f"extension-poll:{extension_id}",
    )


async def poll_source_connection(connection_id: uuid.UUID) -> dict[str, int]:
    """Acquire pages, durably process revisions, then advance the checkpoint."""
    received = 0
    created = 0
    secrets: dict[str, str] = {}
    async with async_session_factory() as session:
        connection = (
            await session.execute(
                select(SourceConnection)
                .where(SourceConnection.id == connection_id)
                .with_for_update()
            )
        ).scalars().first()
        if connection is None or not connection.is_active:
            return {"received": 0, "created": 0}
        now = _now()
        unfinished_recent_sync = (
            connection.status != "error"
            and
            connection.last_sync_started_at is not None
            and (
                connection.last_sync_completed_at is None
                or connection.last_sync_started_at > connection.last_sync_completed_at
            )
            and connection.last_sync_started_at > now - timedelta(hours=2)
        )
        if unfinished_recent_sync:
            logger.info("Source %s already has a sync in progress", connection.id)
            return {"received": 0, "created": 0}
        connection.last_sync_started_at = _now()
        connection.last_sync_error = None
        session.add(connection)
        await session.commit()
        try:
            extension = await session.get(Extension, connection.extension_id)
            if extension is None or not extension.is_active:
                raise ValueError(f"source adapter {connection.extension_id} is unavailable")
            manifest = ExtensionManifest.model_validate(extension.config)
            if "collector" not in manifest.capabilities:
                raise ValueError(f"extension {connection.extension_id} lacks collector capability")
            checkpoints = (
                await session.execute(
                    select(SourceCheckpoint).where(
                        SourceCheckpoint.connection_id == connection.id
                    )
                )
            ).scalars().all()
            checkpoints_by_stream = {item.stream: item for item in checkpoints}
            secrets = await get_source_secrets(session, connection.id)
            current_checkpoint = (
                checkpoints_by_stream["default"].value
                if "default" in checkpoints_by_stream
                else {}
            )

            for _page in range(MAX_PAGES_PER_RUN):
                runtime_config = {
                    "connection_id": str(connection.id),
                    "config": connection.config,
                    "secrets": secrets,
                    "checkpoint": current_checkpoint,
                    "checkpoints": {
                        stream: item.value for stream, item in checkpoints_by_stream.items()
                    },
                }
                result = await run_poller(connection.extension_id, runtime_config)
                received += len(result.records)
                for envelope in result.records:
                    raw_log, was_created = await ingest_log(
                        session,
                        device_id=f"source:{connection.id}",
                        extension_id=connection.extension_id,
                        source_connection_id=connection.id,
                        payload=envelope.payload,
                        client_timestamp=envelope.client_timestamp,
                        client_timezone=envelope.client_timezone,
                        external_key=envelope.external_key,
                        external_revision=envelope.external_revision,
                        source_updated_at=envelope.source_updated_at,
                        update_policy=envelope.update_policy,
                    )
                    await copy_context(
                        session,
                        from_type="source_connection",
                        from_id=connection.id,
                        to_type="raw_log",
                        to_id=raw_log.id,
                    )
                    if was_created or raw_log.processing_status != "done":
                        await process_log(session, raw_log.id)
                    if was_created:
                        created += 1

                if result.next_checkpoint is not None:
                    checkpoint = checkpoints_by_stream.get(result.checkpoint_stream)
                    checkpoint = checkpoint or SourceCheckpoint(
                        connection_id=connection.id,
                        stream=result.checkpoint_stream,
                    )
                    checkpoint.value = result.next_checkpoint
                    checkpoint.version += 1
                    checkpoint.updated_at = _now()
                    session.add(checkpoint)
                    await session.commit()
                    checkpoints_by_stream[result.checkpoint_stream] = checkpoint
                    current_checkpoint = result.next_checkpoint
                if not result.has_more:
                    break
            else:
                logger.warning("Source %s reached the per-run page limit", connection.id)

            connection = await session.get(SourceConnection, connection.id)
            if connection is not None:
                connection.last_sync_completed_at = _now()
                connection.status = "active"
                connection.updated_at = _now()
                session.add(connection)
                await session.commit()
            return {"received": received, "created": created}
        except Exception as exc:
            await session.rollback()
            safe_error = _redact_error(exc, secrets)
            connection = await session.get(SourceConnection, connection_id)
            if connection is not None:
                connection.status = "error"
                connection.last_sync_error = str(safe_error)
                connection.updated_at = _now()
                session.add(connection)
            await record_processing_failure(
                session,
                source_type="source_connection",
                source_id=connection_id,
                stage="poller",
                error=safe_error,
                context={"extension_id": connection.extension_id if connection else None},
            )
            await session.commit()
            logger.error("Source poller failed for %s: %s", connection_id, safe_error)
            raise safe_error from None


async def poll_extension(extension_id: str) -> dict[str, int]:
    """Compatibility runner for pre-connection append-only extensions."""
    async with async_session_factory() as session:
        extension = await session.get(Extension, extension_id)
        if extension is None or not extension.is_active:
            return {"received": 0, "created": 0}
        result = await run_poller(extension_id, {"config": extension.config, "checkpoint": {}, "secrets": {}})
        created_ids = []
        for envelope in result.records:
            log, was_created = await ingest_log(
                session,
                device_id=f"poller:{extension_id}",
                extension_id=extension_id,
                payload=envelope.payload,
                client_timestamp=envelope.client_timestamp,
                client_timezone=envelope.client_timezone,
            )
            if was_created:
                created_ids.append(log.id)
        for log_id in created_ids:
            await process_log(session, log_id)
        return {"received": len(result.records), "created": len(created_ids)}


async def configure_extension_pollers(scheduler, arq_pool=None) -> int:
    """Register connection schedules plus legacy manifest schedules."""
    async with async_session_factory() as session:
        connections = (
            await session.execute(
                select(SourceConnection).where(
                    SourceConnection.is_active == True,
                    SourceConnection.schedule_cron.is_not(None),
                )
            )
        ).scalars().all()
        extensions = (
            await session.execute(
                select(Extension).where(Extension.is_active == True, Extension.scheduler_cron.is_not(None))
            )
        ).scalars().all()
        connected_extension_ids = {connection.extension_id for connection in connections}

    count = 0
    for connection in connections:
        schedule_source_poller(scheduler, connection, arq_pool)
        count += 1
    for extension in extensions:
        manifest = ExtensionManifest.model_validate(extension.config)
        if (
            extension.id in connected_extension_ids
            or "collector" not in manifest.capabilities
            or not extension.scheduler_cron
        ):
            continue
        scheduler.add_job(
            enqueue_legacy_extension_poll,
            CronTrigger.from_crontab(extension.scheduler_cron),
            args=[arq_pool, extension.id],
            id=f"extension-poller:{extension.id}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        count += 1
    return count


def schedule_source_poller(scheduler, connection: SourceConnection, arq_pool=None) -> None:
    """Apply one connection's current schedule to a running scheduler."""
    job_id = f"source-poller:{connection.id}"
    if not connection.is_active or not connection.schedule_cron:
        try:
            scheduler.remove_job(job_id)
        except JobLookupError:
            pass
        return
    scheduler.add_job(
        enqueue_source_poll,
        CronTrigger.from_crontab(connection.schedule_cron),
        args=[arq_pool, connection.id],
        id=job_id,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

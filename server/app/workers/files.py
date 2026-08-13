import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from app.core.database import engine
from app.core.logger import get_logger
from app.models.files import FileAttachment
from app.services.artifacts import process_artifact
from app.services.failures import record_processing_failure

logger = get_logger(__name__)

BATCH_SIZE = 5


async def task_process_file(ctx: dict | None, file_id_str: str) -> None:
    """Durable ARQ entry point for one artifact."""
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        try:
            await process_artifact(session, uuid.UUID(file_id_str))
            await session.commit()
        except Exception as exc:
            await session.rollback()
            await record_processing_failure(
                session,
                source_type="file_attachment",
                source_id=uuid.UUID(file_id_str),
                stage="artifact_processing",
                error=exc,
            )
            await session.commit()
            logger.exception("Artifact processing failed for %s", file_id_str)


async def task_process_file_batch(ctx: dict | None) -> None:
    """Retry a bounded batch of pending or failed artifacts."""
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        files = (
            await session.execute(
                select(FileAttachment)
                .where(FileAttachment.processing_status.in_(["pending", "failed"]))
                .limit(BATCH_SIZE)
            )
        ).scalars().all()
        for attachment in files:
            try:
                await process_artifact(session, attachment.id)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                await record_processing_failure(
                    session,
                    source_type="file_attachment",
                    source_id=attachment.id,
                    stage="artifact_processing",
                    error=exc,
                )
                await session.commit()
                logger.exception("Artifact processing failed for %s", attachment.id)


async def process_single_file(session: AsyncSession, file: FileAttachment) -> None:
    """Compatibility wrapper used by tests and direct orchestration."""
    await process_artifact(session, file.id)

import traceback
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.retrieval import ProcessingFailure


async def record_processing_failure(
    session: AsyncSession,
    *,
    source_type: str,
    source_id: uuid.UUID | None,
    stage: str,
    error: Exception,
    context: dict | None = None,
) -> ProcessingFailure:
    existing = (
        await session.execute(
            select(ProcessingFailure).where(
                ProcessingFailure.source_type == source_type,
                ProcessingFailure.source_id == source_id,
                ProcessingFailure.stage == stage,
                ProcessingFailure.status == "open",
            )
        )
    ).scalars().first()
    failure = existing or ProcessingFailure(
        source_type=source_type,
        source_id=source_id,
        stage=stage,
        error_type=type(error).__name__,
        error_message=str(error),
    )
    if existing:
        failure.attempts += 1
    failure.error_type = type(error).__name__
    failure.error_message = str(error)
    failure.traceback = "".join(traceback.format_exception(error))[-20_000:]
    failure.context = context or {}
    failure.last_failed_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(failure)
    await session.flush()
    return failure

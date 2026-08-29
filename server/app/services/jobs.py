import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.captures import Capture, CaptureArtifact, ProcessingJob
from app.models.files import MemoryProposal

STAGE_DEPENDENCIES = {
    "classification": ("content_extraction",),
    "memory_enrichment": ("content_extraction", "classification"),
}


class StageBlockedError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def start_job(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    stage: str,
    processor: str,
    input_version: int = 1,
    processor_version: str = "1",
    capture_id: uuid.UUID | None = None,
) -> ProcessingJob:
    if capture_id is not None:
        capture = await session.get(Capture, capture_id)
        if capture is not None and capture.status == "cancelled":
            raise StageBlockedError("capture is cancelled")
    required = STAGE_DEPENDENCIES.get(stage, ())
    if required:
        dependencies = (
            await session.execute(
                select(ProcessingJob).where(
                    ProcessingJob.target_type == target_type,
                    ProcessingJob.target_id == target_id,
                    ProcessingJob.input_version == input_version,
                    ProcessingJob.stage.in_(required),
                )
            )
        ).scalars().all()
        by_stage = {dependency.stage: dependency for dependency in dependencies}
        blocked = [
            dependency
            for dependency in required
            if dependency not in by_stage or by_stage[dependency].status != "completed"
        ]
        if blocked:
            raise StageBlockedError(f"{stage} is blocked by: {', '.join(blocked)}")
    job = (
        await session.execute(
            select(ProcessingJob).where(
                ProcessingJob.target_type == target_type,
                ProcessingJob.target_id == target_id,
                ProcessingJob.stage == stage,
                ProcessingJob.input_version == input_version,
            )
        )
    ).scalars().first()
    if job is None:
        job = ProcessingJob(
            target_type=target_type,
            target_id=target_id,
            stage=stage,
            processor=processor,
            input_version=input_version,
            processor_version=processor_version,
            capture_id=capture_id,
        )
    job.status = "running"
    job.attempts += 1
    job.started_at = _now()
    job.completed_at = None
    job.error_type = None
    job.error_message = None
    job.updated_at = _now()
    session.add(job)
    if capture_id is not None:
        capture = await session.get(Capture, capture_id)
        if capture is not None and capture.status not in ("cancelled", "ready"):
            capture.status = "processing"
            capture.updated_at = _now()
            session.add(capture)
    await session.flush()
    return job


async def complete_job(
    session: AsyncSession,
    job: ProcessingJob,
    *,
    output_refs: dict | None = None,
) -> None:
    job.status = "completed"
    job.output_refs = {**job.output_refs, **(output_refs or {})}
    job.completed_at = _now()
    job.updated_at = _now()
    session.add(job)
    await session.flush()


async def fail_job(session: AsyncSession, job: ProcessingJob, error: Exception) -> None:
    job.status = "failed"
    job.error_type = type(error).__name__
    job.error_message = str(error)
    job.completed_at = _now()
    job.updated_at = _now()
    session.add(job)
    later_stages = {
        stage
        for stage, dependencies in STAGE_DEPENDENCIES.items()
        if job.stage in dependencies
    }
    if later_stages:
        blocked_jobs = (
            await session.execute(
                select(ProcessingJob).where(
                    ProcessingJob.target_type == job.target_type,
                    ProcessingJob.target_id == job.target_id,
                    ProcessingJob.input_version == job.input_version,
                    ProcessingJob.stage.in_(later_stages),
                    ProcessingJob.status == "pending",
                )
            )
        ).scalars().all()
        for blocked in blocked_jobs:
            blocked.status = "cancelled"
            blocked.error_type = "DependencyFailed"
            blocked.error_message = f"Blocked by failed {job.stage} stage"
            blocked.completed_at = _now()
            blocked.updated_at = _now()
            session.add(blocked)
    if job.capture_id is not None:
        capture = await session.get(Capture, job.capture_id)
        if capture is not None:
            capture.processing_error = str(error)
            capture.updated_at = _now()
            session.add(capture)
        await refresh_capture_status(session, job.capture_id)
    await session.flush()


async def skip_job(session: AsyncSession, job: ProcessingJob, reason: Exception | str) -> None:
    job.status = "skipped"
    job.error_type = type(reason).__name__ if isinstance(reason, Exception) else "Skipped"
    job.error_message = str(reason)
    job.completed_at = _now()
    job.updated_at = _now()
    session.add(job)
    if job.capture_id is not None:
        await refresh_capture_status(session, job.capture_id)
    await session.flush()


async def refresh_capture_status(session: AsyncSession, capture_id: uuid.UUID) -> Capture | None:
    capture = await session.get(Capture, capture_id)
    if capture is None:
        return None
    if capture.status == "cancelled":
        return capture
    jobs = (
        await session.execute(select(ProcessingJob).where(ProcessingJob.capture_id == capture_id))
    ).scalars().all()
    pending_review = False
    if capture.classification.get("needs_review"):
        pending_review = True
    file_ids = (
        await session.execute(
            select(CaptureArtifact.file_id).where(CaptureArtifact.capture_id == capture_id)
        )
    ).scalars().all()
    if file_ids:
        pending_review = pending_review or (
            await session.execute(
                select(MemoryProposal.id)
                .where(MemoryProposal.file_id.in_(file_ids))
                .where(MemoryProposal.status == "pending")
                .limit(1)
            )
        ).scalars().first() is not None
    if not jobs:
        capture.status = "preserved"
    elif any(job.status in ("pending", "running") for job in jobs):
        capture.status = "processing"
    elif pending_review:
        capture.status = "awaiting_review"
    elif any(job.status in ("failed", "skipped") for job in jobs):
        capture.status = "partially_ready" if any(job.status == "completed" for job in jobs) else "failed"
    else:
        capture.status = "ready"
    capture.updated_at = _now()
    session.add(capture)
    await session.flush()
    return capture

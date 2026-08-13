import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_session
from app.core.dependencies import get_current_superuser
from app.core.logger import get_logger
from app.models.accounting import AIUsage
from app.models.auth import User
from app.models.config import Prompt
from app.models.processing import Session
from app.models.retrieval import ProcessingFailure

logger = get_logger(__name__)

router = APIRouter()


class PromptCreate(BaseModel):
    name: str
    template: str
    version: int = 1


class PromptResponse(BaseModel):
    id: str
    name: str
    template: str
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("/admin/prompts")
async def list_prompts(
    current_user: User = Depends(get_current_superuser),
    db_session: AsyncSession = Depends(get_session),
):
    statement = select(Prompt).order_by(Prompt.name, Prompt.version.desc())
    result = await db_session.execute(statement)
    return result.scalars().all()


@router.post("/admin/prompts", status_code=status.HTTP_201_CREATED)
async def create_prompt(
    body: PromptCreate,
    current_user: User = Depends(get_current_superuser),
    db_session: AsyncSession = Depends(get_session),
):
    prompt = Prompt(
        name=body.name,
        template=body.template,
        version=body.version,
        is_active=True,
    )
    db_session.add(prompt)
    await db_session.commit()
    await db_session.refresh(prompt)
    return prompt


@router.post("/admin/process/sessionize")
async def trigger_sessionizer(
    current_user: User = Depends(get_current_superuser),
    db_session: AsyncSession = Depends(get_session),
):
    from app.services.processing import run_processing_pipeline

    result = await run_processing_pipeline(db_session)
    return result


@router.post("/admin/process/memory")
async def trigger_memory_backfill(
    limit: int = 500,
    current_user: User = Depends(get_current_superuser),
    db_session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    if not 1 <= limit <= 5000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 5000")
    from app.services.extraction import backfill_event_facts

    result = await backfill_event_facts(db_session, limit=limit)
    await db_session.commit()
    return result


@router.post("/admin/process/timeline")
async def trigger_timeline(
    limit: int = 10,
    current_user: User = Depends(get_current_superuser),
    db_session: AsyncSession = Depends(get_session),
):
    from app.services.timeline import process_pending_sessions

    count = await process_pending_sessions(db_session, limit=limit)
    return {"entries_generated": count}


@router.post("/admin/process/summarize/{logical_date}")
async def trigger_summary(
    logical_date: str,
    force: bool = False,
    current_user: User = Depends(get_current_superuser),
    db_session: AsyncSession = Depends(get_session),
):
    from app.services.summarizer import generate_daily_summary

    try:
        datetime.strptime(logical_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    summary = await generate_daily_summary(db_session, logical_date, force=force)
    return summary


@router.get("/admin/usage")
async def get_ai_usage(
    days: int = 7,
    current_user: User = Depends(get_current_superuser),
    db_session: AsyncSession = Depends(get_session),
):
    if not 1 <= days <= 3650:
        raise HTTPException(status_code=400, detail="days must be between 1 and 3650")
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    statement = (
        select(AIUsage)
        .where(AIUsage.created_at >= cutoff)
        .order_by(AIUsage.created_at.desc())
    )
    result = await db_session.execute(statement)
    records = result.scalars().all()

    totals = {
        "total_input_tokens": sum(r.input_tokens for r in records),
        "total_output_tokens": sum(r.output_tokens for r in records),
        "total_cost": sum(r.cost for r in records),
        "total_calls": len(records),
    }
    return {"records": records, "totals": totals}


@router.get("/admin/sessions")
async def list_sessions(
    status_filter: str | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_superuser),
    db_session: AsyncSession = Depends(get_session),
):
    statement = select(Session)
    if status_filter:
        statement = statement.where(Session.status == status_filter)
    statement = statement.order_by(Session.start_time.desc()).limit(limit)
    result = await db_session.execute(statement)
    return result.scalars().all()


@router.get("/admin/failures", response_model=list[ProcessingFailure])
async def list_processing_failures(
    failure_status: str = "open",
    limit: int = 100,
    current_user: User = Depends(get_current_superuser),
    db_session: AsyncSession = Depends(get_session),
) -> list[ProcessingFailure]:
    statement = (
        select(ProcessingFailure)
        .where(ProcessingFailure.status == failure_status)
        .order_by(ProcessingFailure.last_failed_at.desc())
        .limit(min(max(limit, 1), 1000))
    )
    return list((await db_session.execute(statement)).scalars().all())


@router.post("/admin/failures/{failure_id}/retry", response_model=ProcessingFailure)
async def retry_processing_failure(
    failure_id: uuid.UUID,
    current_user: User = Depends(get_current_superuser),
    db_session: AsyncSession = Depends(get_session),
) -> ProcessingFailure:
    failure = await db_session.get(ProcessingFailure, failure_id)
    if failure is None:
        raise HTTPException(status_code=404, detail="Failure not found")
    if failure.source_id is None:
        raise HTTPException(status_code=400, detail="This failure requires its extension scheduler to retry")
    if failure.source_type == "raw_log":
        from app.workers.process import process_log

        await process_log(db_session, failure.source_id)
    elif failure.source_type == "file_attachment":
        from app.services.artifacts import process_artifact

        await process_artifact(db_session, failure.source_id, force=True)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported retry source: {failure.source_type}")
    failure.status = "resolved"
    failure.resolved_at = datetime.now(UTC).replace(tzinfo=None)
    db_session.add(failure)
    await db_session.commit()
    await db_session.refresh(failure)
    return failure


@router.post("/admin/failures/{failure_id}/resolve", response_model=ProcessingFailure)
async def resolve_processing_failure(
    failure_id: uuid.UUID,
    current_user: User = Depends(get_current_superuser),
    db_session: AsyncSession = Depends(get_session),
) -> ProcessingFailure:
    failure = await db_session.get(ProcessingFailure, failure_id)
    if failure is None:
        raise HTTPException(status_code=404, detail="Failure not found")
    failure.status = "resolved"
    failure.resolved_at = datetime.now(UTC).replace(tzinfo=None)
    db_session.add(failure)
    await db_session.commit()
    await db_session.refresh(failure)
    return failure

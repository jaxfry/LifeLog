from datetime import datetime, timezone
from typing import Optional

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
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None)
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
    status_filter: Optional[str] = None,
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

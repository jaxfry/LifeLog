from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import logging

from ..dependencies import get_session
from ..services import ProcessingService, ProcessingRoutingService
from ..core.actors import actor_registry
from ..core.config import settings
from ..auth import require_auth  # Add authentication for internal APIs

router = APIRouter(
    prefix="/processing",
    tags=["Processing"],
)

logger = logging.getLogger(__name__)

@router.post("/trigger/{raw_log_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_processing(
    raw_log_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)  # Protect internal API
):
    """
    Manually triggers the processing pipeline for a single raw log.
    Uses service layer to abstract database operations.
    NOTE: In production, this will be replaced by an async task queue.
    """
    # Use service layer to get raw log with source actor
    raw_log = await ProcessingService.get_raw_log_with_source_actor(session, raw_log_id)
    
    if not raw_log:
        raise HTTPException(status_code=404, detail="RawLog not found")

    # Resolve processor via DB mapping, fallback to config
    source_actor_slug = raw_log.source_actor.slug
    processor_slug = await ProcessingRoutingService.resolve_processor_slug(session, source_actor_slug)

    if not processor_slug:
        return {"status": "ok", "detail": f"No processor mapped for source '{source_actor_slug}'"}

    # Get the actor's logic class from the registry
    ActorClass = actor_registry.get_actor_class(processor_slug)
    if not ActorClass:
        raise HTTPException(
            status_code=500,
            detail=f"Code for actor '{processor_slug}' not registered."
        )

    # Instantiate the actor and run it
    actor_instance = ActorClass()
    await actor_instance.run(data=raw_log)

    return {"status": "processing triggered"}


class DateRangeFilter(BaseModel):
    """Date range filter for reprocessing."""
    start: Optional[datetime] = None
    end: Optional[datetime] = None


class ReprocessActorRequest(BaseModel):
    """Request to reprocess actor data."""
    date_range: Optional[DateRangeFilter] = None
    dry_run: bool = True  # Safety default: don't actually reprocess unless explicit


class ReprocessActorResponse(BaseModel):
    """Response after queuing actor reprocessing."""
    message: str
    actor_slug: str
    current_version: str
    raw_logs_queued: int
    date_range: Optional[dict] = None


class CostEstimateResponse(BaseModel):
    """Response with cost estimation for reprocessing."""
    raw_logs_affected: int
    estimated_ai_calls: int
    estimated_cost_usd: float
    estimated_duration_minutes: int
    current_version: str
    date_range: Optional[dict] = None


@router.post("/estimate/{actor_slug}", response_model=CostEstimateResponse)
async def estimate_reprocessing_cost(
    actor_slug: str,
    request: Optional[ReprocessActorRequest] = None,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Estimate the cost and scope of reprocessing before actually doing it.
    
    This endpoint helps users make informed decisions about whether to reprocess
    historical data after an extension upgrade. It calculates:
    - Number of raw_logs affected
    - Estimated AI API calls (and cost)
    - Estimated processing time
    
    Use this before calling reprocess-actor to understand the impact.
    """
    try:
        start_date = None
        end_date = None
        if request and request.date_range:
            start_date = request.date_range.start
            end_date = request.date_range.end
        
        estimate = await ProcessingService.estimate_reprocessing_cost(
            session,
            actor_slug,
            start_date=start_date,
            end_date=end_date
        )
        
        return CostEstimateResponse(**estimate)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/reprocess-actor/{actor_slug}", response_model=ReprocessActorResponse, status_code=status.HTTP_202_ACCEPTED)
async def reprocess_actor(
    actor_slug: str,
    request: ReprocessActorRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Queue reprocessing for raw_logs previously processed by older versions of an actor.
    
    This endpoint is typically called after an extension upgrade to regenerate events
    with the new actor logic. The original events are superseded, not deleted.
    
    **Safety Features**:
    - `dry_run=true` (default): Only estimates, doesn't actually reprocess
    - `date_range`: Optionally limit reprocessing to a specific time window
    
    **Workflow**:
    1. Call `/estimate/{actor_slug}` to see cost/scope
    2. If acceptable, call this endpoint with `dry_run=false`
    3. Monitor progress via processing logs
    
    **Note**: This uses background tasks. In production, use a proper queue (Celery/RQ).
    """
    from sqlmodel import select
    from .. import models
    
    # Get the actor and its current version
    actor_stmt = select(models.Actor).where(models.Actor.slug == actor_slug)
    actor = (await session.exec(actor_stmt)).one_or_none()
    if not actor:
        raise HTTPException(status_code=404, detail=f"Actor '{actor_slug}' not found")

    current_version = actor.version
    
    # Extract date range if provided
    start_date = None
    end_date = None
    if request.date_range:
        start_date = request.date_range.start
        end_date = request.date_range.end

    # Find raw_logs to reprocess
    raw_log_ids = await ProcessingService.find_raw_logs_for_reprocessing(
        session,
        actor_slug,
        current_version,
        start_date=start_date,
        end_date=end_date
    )

    if not raw_log_ids:
        return ReprocessActorResponse(
            message=f"No raw_logs found for reprocessing (all already at version {current_version})",
            actor_slug=actor_slug,
            current_version=current_version,
            raw_logs_queued=0,
            date_range={
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            } if (start_date or end_date) else None
        )
    
    # If dry_run, just return the estimate
    if request.dry_run:
        return ReprocessActorResponse(
            message=f"[DRY RUN] Would queue {len(raw_log_ids)} raw_logs for reprocessing. Set dry_run=false to execute.",
            actor_slug=actor_slug,
            current_version=current_version,
            raw_logs_queued=len(raw_log_ids),
            date_range={
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            } if (start_date or end_date) else None
        )

    # Background task to reprocess each raw_log
    async def _reprocess_raw_logs():
        from ..db import async_session
        for raw_log_id in raw_log_ids:
            async with async_session() as bg_session:
                raw_log = await ProcessingService.get_raw_log_with_source_actor(bg_session, raw_log_id)
                if not raw_log:
                    continue

                ActorClass = actor_registry.get_actor_class(actor_slug)
                if not ActorClass:
                    logger.warning(f"Actor code '{actor_slug}' not registered; skipping raw_log_id={raw_log_id}")
                    continue

                try:
                    actor_instance = ActorClass()
                    await actor_instance.run(data=raw_log)
                except Exception as e:
                    logger.error(f"Reprocessing failed for raw_log_id={raw_log_id}: {e}")

    background_tasks.add_task(_reprocess_raw_logs)

    return ReprocessActorResponse(
        message=f"Queued {len(raw_log_ids)} raw_logs for reprocessing with actor version {current_version}",
        actor_slug=actor_slug,
        current_version=current_version,
        raw_logs_queued=len(raw_log_ids),
        date_range={
            "start": start_date.isoformat() if start_date else None,
            "end": end_date.isoformat() if end_date else None
        } if (start_date or end_date) else None
    )
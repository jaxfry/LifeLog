from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel
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


class ReprocessActorResponse(BaseModel):
    """Response after queuing actor reprocessing."""
    message: str
    actor_slug: str
    current_version: str
    raw_logs_queued: int


@router.post("/reprocess-actor/{actor_slug}", response_model=ReprocessActorResponse, status_code=status.HTTP_202_ACCEPTED)
async def reprocess_actor(
    actor_slug: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Queue reprocessing for all raw_logs previously processed by older versions of an actor.
    
    This endpoint is typically called after an extension upgrade to regenerate events
    with the new actor logic. The original events are superseded, not deleted.
    """
    from sqlmodel import select
    from .. import models
    
    # Get the actor and its current version
    actor_stmt = select(models.Actor).where(models.Actor.slug == actor_slug)
    actor = (await session.exec(actor_stmt)).one_or_none()
    if not actor:
        raise HTTPException(status_code=404, detail=f"Actor '{actor_slug}' not found")

    current_version = actor.version

    # Find raw_logs to reprocess
    raw_log_ids = await ProcessingService.find_raw_logs_for_reprocessing(
        session,
        actor_slug,
        current_version
    )

    if not raw_log_ids:
        return ReprocessActorResponse(
            message=f"No raw_logs found for reprocessing (all already at version {current_version})",
            actor_slug=actor_slug,
            current_version=current_version,
            raw_logs_queued=0
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
        raw_logs_queued=len(raw_log_ids)
    )
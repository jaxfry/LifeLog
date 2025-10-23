from fastapi import APIRouter, Depends, HTTPException, status
import asyncio
from sqlmodel.ext.asyncio.session import AsyncSession  # <-- Use AsyncSession

from .. import models, schemas
from ..dependencies import get_session
from ..auth import device_auth_dependency, require_auth
from typing import cast
from ..services import IngestionService

# Create a router, which is like a mini-FastAPI app
router = APIRouter(
    prefix="/ingest",
    tags=["Ingestion"],
)

@router.post("/", response_model=schemas.IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_raw_log(
    *,
    log_in: schemas.RawLogIn,
    session: AsyncSession = Depends(get_session),
    device = Depends(device_auth_dependency),  # Device-level auth for ingestion
):
    """
    The primary endpoint for ingesting raw data from client collectors.
    Uses service layer to abstract database operations.
    """
    # Use service layer to find the actor
    actor = await IngestionService.find_source_actor(session, log_in.source_actor_slug)
    
    if not actor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source actor with slug '{log_in.source_actor_slug}' not found."
        )

    if actor.actor_type != models.ActorType.SOURCE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Actor '{log_in.source_actor_slug}' is not of type SOURCE."
        )

    # Safety: ensure DB-loaded actor has an ID
    if actor.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Actor record is invalid (missing id)."
        )

    # Use service layer to create the raw log
    db_raw_log = await IngestionService.create_raw_log(
        session,
        cast(int, actor.id),
        log_in.data,
        device_id=device.id,
    )

    if db_raw_log.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create raw log (missing id).",
        )

    # Kick off background processing (auto-routing to processor if configured)
    async def _process_raw_log_task(raw_log_id: int):
        from ..services import ProcessingService, ProcessingRoutingService
        from ..core.actors import actor_registry
        from ..db import async_session

        async with async_session() as bg_session:
            # Load raw log with source actor
            raw_log = await ProcessingService.get_raw_log_with_source_actor(bg_session, raw_log_id)
            if not raw_log:
                return

            source_actor_slug = raw_log.source_actor.slug
            processor_slug = await ProcessingRoutingService.resolve_processor_slug(bg_session, source_actor_slug)
            if not processor_slug:
                # No processor mapped; nothing to do
                return

            ActorClass = actor_registry.get_actor_class(processor_slug)
            if not ActorClass:
                # Code not registered
                return

            try:
                actor_instance = ActorClass()
                await actor_instance.run(data=raw_log)
            except Exception as e:
                # Swallow exceptions to avoid affecting API response; logs are written inside actor
                print(f"Auto-processing failed for raw_log_id={raw_log_id}: {e}")

    # Schedule the async processing task (fire-and-forget)
    try:
        asyncio.create_task(_process_raw_log_task(db_raw_log.id))
    except RuntimeError:
        # Event loop not ready; skip auto-processing (manual trigger remains available)
        pass

    return schemas.IngestResponse(
        message=f"Data from '{log_in.source_actor_slug}' ingested successfully.",
        raw_log_id=db_raw_log.id
    )
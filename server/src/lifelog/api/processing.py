from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from ..dependencies import get_session
from ..services import ProcessingService
from ..core.actors import actor_registry
from ..auth import require_auth  # Add authentication for internal APIs

router = APIRouter(
    prefix="/processing",
    tags=["Processing"],
)

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

    # This is our temporary routing logic. A real system would have a
    # configurable mapping from source actors to processor actors.
    # TODO: Implement a dynamic routing system.
    routing_map = {
        "test-source": "test-processor"
    }

    source_actor_slug = raw_log.source_actor.slug
    processor_slug = routing_map.get(source_actor_slug)

    if not processor_slug:
        # If no processor is mapped, we can skip or log a warning.
        # For now, we'll just return a success message.
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
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload

from ..dependencies import get_session
from .. import models
from ..core.actors import actor_registry

router = APIRouter(
    prefix="/processing",
    tags=["Processing"],
)

@router.post("/trigger/{raw_log_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_processing(
    raw_log_id: int,
    session: AsyncSession = Depends(get_session)
):
    """
    Manually triggers the processing pipeline for a single raw log.
    NOTE: In production, this will be replaced by an async task queue.
    """
    raw_log = await session.get(models.RawLog, raw_log_id)
    if raw_log:
        # Eagerly load the source_actor relationship
        await session.refresh(raw_log, attribute_names=["source_actor"])
    if not raw_log:
        raise HTTPException(status_code=404, detail="RawLog not found")

    # This is our temporary routing logic. A real system would have a
    # configurable mapping from source actors to processor actors.
    # This is our temporary routing logic. A real system would have a
    # configurable mapping from source actors to processor actors.
    # For now, we'll hardcode a mapping for the test extension.
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
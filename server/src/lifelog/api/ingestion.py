from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession  # <-- Use AsyncSession
from sqlmodel import select  # <-- Import select from sqlmodel directly

from .. import models, schemas
from ..dependencies import get_session

# Create a router, which is like a mini-FastAPI app
router = APIRouter(
    prefix="/ingest",
    tags=["Ingestion"],
)

# The function signature must now be `async def`

@router.post("/", response_model=schemas.IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_raw_log(
    *,
    log_in: schemas.RawLogIn,
    session: AsyncSession = Depends(get_session)
):
    """
    The primary endpoint for ingesting raw data from client collectors.
    """
    # We already have the slug we need for the response message. Let's store it.
    source_slug = log_in.source_actor_slug

    statement = select(models.Actor).where(models.Actor.slug == source_slug)
    result = await session.exec(statement)
    actor = result.first()

    if not actor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source actor with slug '{source_slug}' not found."
        )

    if actor.actor_type != models.ActorType.SOURCE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Actor '{source_slug}' is not of type SOURCE."
        )

    db_raw_log = models.RawLog(
        source_actor_id=actor.id,
        device_id=None,
        raw_data=log_in.data
    )

    session.add(db_raw_log)
    await session.commit()
    await session.refresh(db_raw_log)

    # Now, we use the variable we saved before the commit.
    # This avoids any lazy loading on the potentially expired `actor` object.
    return schemas.IngestResponse(
        message=f"Data from '{source_slug}' ingested successfully.",
        raw_log_id=db_raw_log.id
    )
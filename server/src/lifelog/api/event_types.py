from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..dependencies import get_session
from .. import models, schemas

router = APIRouter(
    prefix="/event-types",
    tags=["Event Types"],
)

@router.post("/", response_model=schemas.EventTypeRead, status_code=status.HTTP_201_CREATED)
async def create_event_type(
    event_type_in: schemas.EventTypeCreate,
    # For now, we'll pass the owner_id as a query param.
    # Later, this could be inferred from an authenticated extension.
    owner_extension_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Creates a new EventType owned by a specific Extension."""
    # Verify owner extension exists
    owner = await session.get(models.Extension, owner_extension_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Owner extension not found.")

    db_event_type = models.EventType.model_validate(
        event_type_in, update={"owner_extension_id": owner_extension_id}
    )
    session.add(db_event_type)
    await session.commit()
    await session.refresh(db_event_type)
    return db_event_type
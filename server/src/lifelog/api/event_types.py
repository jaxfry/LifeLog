from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..dependencies import get_session
from .. import models, schemas
from ..auth import require_auth

router = APIRouter(
    prefix="/event-types",
    tags=["Event Types"],
)

@router.post("/", response_model=schemas.EventTypeRead, status_code=status.HTTP_201_CREATED)
async def create_event_type(
    event_type_in: schemas.EventTypeCreate,
    owner_extension_id: int | None = Query(None, description="Owner extension id"),
    owner_extension_slug: str | None = Query(None, description="Owner extension slug"),
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    """Creates a new EventType owned by a specific Extension."""
    # Verify owner extension exists
    if owner_extension_id is not None:
        owner = await session.get(models.Extension, owner_extension_id)
    elif owner_extension_slug is not None:
        from sqlmodel import select
        owner = (await session.exec(select(models.Extension).where(models.Extension.slug == owner_extension_slug))).one_or_none()
    else:
        owner = None
    if not owner:
        raise HTTPException(status_code=404, detail="Owner extension not found.")

    db_event_type = models.EventType.model_validate(
        event_type_in, update={"owner_extension_id": owner.id}
    )
    session.add(db_event_type)
    await session.commit()
    await session.refresh(db_event_type)
    return db_event_type


@router.get("/", response_model=list[schemas.EventTypeRead])
async def list_event_types(
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """List all event types (internal management)."""
    from sqlmodel import select
    result = await session.exec(select(models.EventType))
    return result.all()
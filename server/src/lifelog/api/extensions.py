from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import selectinload

from ..dependencies import get_session
from .. import models, schemas

router = APIRouter(
    prefix="/extensions",
    tags=["extensions"],
)

@router.post("/", response_model=schemas.ExtensionRead, status_code=status.HTTP_201_CREATED)
async def create_extension(
    *,
    extension_in: schemas.ExtensionCreate,
    session: AsyncSession = Depends(get_session)
):
    """Register a new extension along with its associated actors."""
    # Check for existing extension
    statement = select(models.Extension).where(models.Extension.slug == extension_in.slug)
    result = await session.exec(statement)
    if result.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Extension with slug '{extension_in.slug}' already exists."
        )
    
    # Create extension and actors
    extension_data = extension_in.model_dump(exclude={'actors'})
    db_extension = models.Extension(**extension_data)

    for actor_in in extension_in.actors:
        db_actor = models.Actor.model_validate(actor_in)
        db_extension.actors.append(db_actor)

    session.add(db_extension)
    await session.flush()
    extension_id = db_extension.id
    await session.commit()
    
    # Fetch with relationships loaded
    statement = select(models.Extension).where(
        models.Extension.id == extension_id
    ).options(selectinload(models.Extension.actors))
    result = await session.exec(statement)
    
    return result.one()

@router.get("/", response_model=list[schemas.ExtensionRead])
async def get_extensions(session: AsyncSession = Depends(get_session)):
    """List all registered extensions."""
    statement = select(models.Extension).options(selectinload(models.Extension.actors))
    result = await session.exec(statement)
    return result.all()
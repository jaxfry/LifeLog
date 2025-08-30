from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from ..dependencies import get_session
from .. import schemas
from ..services import ExtensionService
from ..auth import require_auth  # Add authentication for internal APIs

router = APIRouter(
    prefix="/extensions",
    tags=["extensions"],
)

@router.post("/", response_model=schemas.ExtensionRead, status_code=status.HTTP_201_CREATED)
async def create_extension(
    *,
    extension_in: schemas.ExtensionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)  # Protect internal API
):
    """Register a new extension along with its associated actors using service layer."""
    try:
        # Use service layer to create extension with actors
        extension_data = extension_in.model_dump(exclude={'actors'})
        actors_data = [actor.model_dump() for actor in extension_in.actors]
        
        db_extension = await ExtensionService.create_extension_with_actors(
            session, extension_data, actors_data
        )
        
        return db_extension
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )

@router.get("/", response_model=list[schemas.ExtensionRead])
async def get_extensions(
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)  # Protect internal API
):
    """List all registered extensions using service layer."""
    extensions = await ExtensionService.get_extensions_with_actors(session)
    return extensions
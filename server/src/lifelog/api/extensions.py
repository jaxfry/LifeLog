from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel
from typing import Optional

from ..dependencies import get_session
from .. import schemas
from ..services import ExtensionService
from ..auth import require_auth  # Add authentication for internal APIs
from ..manifest import ExtensionManifest

router = APIRouter(
    prefix="/extensions",
    tags=["extensions"],
)


class ManifestInstallRequest(BaseModel):
    """Request to install/update an extension from manifest."""
    manifest: ExtensionManifest
    update_if_exists: bool = False


class ManifestInstallResponse(BaseModel):
    """Response after installing/updating an extension from manifest."""
    message: str
    extension_slug: str
    version: str
    is_upgrade: bool
    actors_registered: int
    event_types_registered: int

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


@router.post("/from-manifest", response_model=ManifestInstallResponse, status_code=status.HTTP_201_CREATED)
async def install_extension_from_manifest(
    request: ManifestInstallRequest,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Install or update an extension from a manifest.json structure.
    
    This is the primary way to register extensions declaratively as per architecture v3.3.
    Handles actor registration, event type creation, prompt templates, and version upgrades.
    
    If update_if_exists=True and the version changed, old raw_logs may be queued for reprocessing.
    """
    try:
        extension, is_upgrade = await ExtensionService.create_extension_from_manifest(
            session,
            request.manifest,
            update_if_exists=request.update_if_exists
        )
        
        # Count registered components
        actors_count = len(request.manifest.server_side.actors) if request.manifest.server_side and request.manifest.server_side.actors else 0
        event_types_count = len(request.manifest.server_side.event_types) if request.manifest.server_side and request.manifest.server_side.event_types else 0
        
        message = f"Extension '{extension.slug}' version {extension.version} "
        if is_upgrade:
            message += "upgraded successfully. Actors may require reprocessing."
        else:
            message += "installed successfully."
        
        return ManifestInstallResponse(
            message=message,
            extension_slug=extension.slug,
            version=extension.version,
            is_upgrade=is_upgrade,
            actors_registered=actors_count,
            event_types_registered=event_types_count
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
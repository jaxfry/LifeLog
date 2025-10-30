from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

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


class InstalledExtensionResponse(BaseModel):
    """Response for client sync: installed extensions with their manifests."""
    slug: str
    name: str
    version: str
    is_active: bool
    client_manifest: Optional[Dict[str, Any]] = None  # The client_side section
    server_manifest: Optional[Dict[str, Any]] = None  # The server_side section (for debugging)


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


@router.get("/installed", response_model=List[InstalledExtensionResponse])
async def get_installed_extensions(
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Get all installed extensions with their client-side manifests.
    
    This endpoint is used by client applications to synchronize installed extensions
    and deploy client-side components (collectors, UI components).
    
    **Client Sync Workflow**:
    1. Client polls this endpoint periodically (e.g., every 5 minutes)
    2. For new/updated extensions, downloads components from server
    3. Installs collectors as background processes
    4. Registers UI components for rendering
    
    **Response includes**:
    - Full extension metadata (slug, version, active status)
    - client_side manifest (collectors, UI components per platform)
    - server_side manifest (for debugging/transparency)
    """
    from sqlmodel import select
    from .. import models
    
    # Get all extensions with their config
    stmt = select(models.Extension).where(models.Extension.is_active == True)
    result = await session.exec(stmt)
    extensions = result.all()
    
    response = []
    for ext in extensions:
        # Extract client_side and server_side from stored config
        # (These were saved during manifest installation)
        config = ext.config or {}
        
        response.append(InstalledExtensionResponse(
            slug=ext.slug,
            name=ext.name,
            version=ext.version,
            is_active=ext.is_active,
            client_manifest=config.get("client_side"),
            server_manifest=config.get("server_side")
        ))
    
    return response



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
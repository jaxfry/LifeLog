from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from ..dependencies import get_session
from .. import schemas
from ..services import ExtensionService
from ..auth import require_auth  # Add authentication for internal APIs
from ..manifest import ExtensionManifest
from ..core.extension_uploader import store_and_register_extension, ExtensionUploadError
from ..core.config import settings
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

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
@router.post("/upload", response_model=ManifestInstallResponse, status_code=status.HTTP_201_CREATED)
async def upload_extension_package(
    package: UploadFile = File(..., description="Signed .lifelog-ext zip archive"),
    signature: UploadFile | None = File(None, description="Detached signature bytes (Ed25519)"),
    approve: bool = Form(True),
    update_if_exists: bool = Form(True),
    current_user: str = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
):
    try:
        archive_bytes = await package.read()
        sig_bytes = await signature.read() if signature is not None else None
        manifest, extracted_path = store_and_register_extension(archive_bytes, sig_bytes)

        # Mark execution as external in stored config
        if manifest.config is None:
            manifest.config = {}
        manifest.config["execution_mode"] = "external"
        manifest.config["store_path"] = str(extracted_path)

        # Register manifest into DB (reuse existing flow)
        extension, is_upgrade = await ExtensionService.create_extension_from_manifest(
            session, manifest, update_if_exists=update_if_exists
        )

        # Newly uploaded extensions remain inactive until approved
        if not approve:
            extension.is_active = False
            session.add(extension)
            await session.commit()
            await session.refresh(extension)

        actors_count = len(manifest.server_side.actors) if manifest.server_side and manifest.server_side.actors else 0
        event_types_count = len(manifest.server_side.event_types) if manifest.server_side and manifest.server_side.event_types else 0
        msg = f"Extension '{extension.slug}' version {extension.version} "
        msg += "installed successfully." if not is_upgrade else "upgraded successfully. Actors may require reprocessing."
        return ManifestInstallResponse(
            message=msg,
            extension_slug=extension.slug,
            version=extension.version,
            is_upgrade=is_upgrade,
            actors_registered=actors_count,
            event_types_registered=event_types_count,
        )
    except ExtensionUploadError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ApproveExtensionRequest(BaseModel):
    approve: bool = True


@router.post("/{slug}/approve", status_code=status.HTTP_200_OK)
async def approve_extension(
    slug: str,
    request: ApproveExtensionRequest,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    """
    Approve or reject an extension (legacy endpoint, use enable/disable instead).
    """
    from sqlmodel import select
    from .. import models
    ext = (await session.exec(select(models.Extension).where(models.Extension.slug == slug))).one_or_none()
    if not ext:
        raise HTTPException(status_code=404, detail="Extension not found")
    ext.is_active = bool(request.approve)
    session.add(ext)
    await session.commit()
    return {"slug": ext.slug, "is_active": ext.is_active, "message": f"Extension {'enabled' if ext.is_active else 'disabled'}"}


@router.post("/{slug}/enable", status_code=status.HTTP_200_OK)
async def enable_extension(
    slug: str,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    """
    Enable an extension.
    
    Note: Requires server restart to load the extension's code and actors.
    """
    try:
        ext = await ExtensionService.toggle_extension_status(session, slug, is_active=True)
        
        # Check if already loaded in memory
        from ..core.extension_loader import get_extension_loader
        try:
            loader = get_extension_loader()
            is_loaded = slug in loader.list_loaded_extensions()
        except RuntimeError:
            is_loaded = False
        
        message = f"Extension '{slug}' enabled."
        if not is_loaded:
            message += " Restart server to activate."
        else:
            message += " Already loaded in memory."
        
        return {
            "slug": ext.slug,
            "is_active": ext.is_active,
            "is_loaded": is_loaded,
            "message": message,
            "requires_restart": not is_loaded
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class ExtensionErrorItem(BaseModel):
    extension_slug: str
    error_type: str
    error_message: str
    occurred_at: datetime
    stack_trace: Optional[str] = None
    resolved: bool = False


class ExtensionErrorListResponse(BaseModel):
    errors: list[ExtensionErrorItem]
    total: int


@router.get("/errors", response_model=ExtensionErrorListResponse)
async def list_extension_errors(
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    List recent extension load errors across all extensions.
    """
    from ..services import ExtensionErrorService
    records = await ExtensionErrorService.get_errors(session, limit=limit, offset=offset)
    items = [
        ExtensionErrorItem(
            extension_slug=r.extension_slug,
            error_type=r.error_type,
            error_message=r.error_message,
            occurred_at=r.occurred_at,
            stack_trace=r.stack_trace,
            resolved=r.resolved,
        ) for r in records
    ]
    return ExtensionErrorListResponse(errors=items, total=len(items))


@router.get("/{slug}/errors", response_model=ExtensionErrorListResponse)
async def get_extension_errors(
    slug: str,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    List recent load errors for a specific extension.
    """
    from ..services import ExtensionErrorService
    records = await ExtensionErrorService.get_errors(session, extension_slug=slug, limit=limit, offset=offset)
    items = [
        ExtensionErrorItem(
            extension_slug=r.extension_slug,
            error_type=r.error_type,
            error_message=r.error_message,
            occurred_at=r.occurred_at,
            stack_trace=r.stack_trace,
            resolved=r.resolved,
        ) for r in records
    ]
    return ExtensionErrorListResponse(errors=items, total=len(items))


@router.post("/{slug}/disable", status_code=status.HTTP_200_OK)
async def disable_extension(
    slug: str,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    """
    Disable an extension.
    
    This disables the extension in the database and attempts to unload it
    from memory immediately. Runs the on_deactivate lifecycle hook if defined.
    
    Note: Actors remain registered in actor_registry but won't be used for
    new processing. Existing routes to these actors should be removed separately.
    """
    try:
        ext = await ExtensionService.toggle_extension_status(session, slug, is_active=False)
        
        # Attempt to unload extension from memory
        was_loaded = False
        unload_successful = False
        
        try:
            from ..core.extension_loader import get_extension_loader
            loader = get_extension_loader()
            was_loaded = slug in loader.list_loaded_extensions()
            
            if was_loaded:
                # Unload will call on_deactivate lifecycle hook
                unload_successful = await loader.unload_extension(slug, session=session)
                
        except RuntimeError as e:
            logger.warning(f"Extension loader not initialized: {e}")
        except Exception as e:
            logger.error(f"Failed to unload extension '{slug}': {e}", exc_info=True)
        
        # Build response message
        message = f"Extension '{slug}' disabled in database."
        if was_loaded:
            if unload_successful:
                message += " Successfully unloaded from memory."
            else:
                message += " Warning: Failed to unload from memory. Server restart recommended."
        else:
            message += " Was not loaded in memory."
        
        return {
            "slug": ext.slug,
            "is_active": ext.is_active,
            "was_loaded": was_loaded,
            "unloaded": unload_successful,
            "message": message,
            "requires_restart": was_loaded and not unload_successful
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{slug}/rollback", status_code=status.HTTP_200_OK)
async def rollback_extension(
    slug: str,
    version: str,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    from sqlmodel import select
    from .. import models
    ext = (await session.exec(select(models.Extension).where(models.Extension.slug == slug))).one_or_none()
    if not ext:
        raise HTTPException(status_code=404, detail="Extension not found")
    # Ensure we have this version on disk
    store_root = Path(settings.EXTENSIONS_STORE_PATH)
    expected = store_root / f"{slug}-{version}"
    if not expected.exists():
        raise HTTPException(status_code=404, detail="Requested version assets not found in store")
    # Update extension version and point store_path to the requested version's directory
    ext.version = version
    # Ensure config exists
    cfg = ext.config or {}
    cfg["store_path"] = str(expected)
    # Preserve existing execution_mode and other keys
    ext.config = cfg
    # Optionally keep ext.is_active as-is
    session.add(ext)
    await session.commit()
    return {"slug": ext.slug, "version": ext.version}


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


@router.get("/status", status_code=status.HTTP_200_OK)
async def get_extensions_status(
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Get the runtime status of all extensions.
    
    Shows which extensions are:
    - Registered in DB
    - Currently loaded in memory (active)
    - Available on filesystem
    
    Useful for debugging extension loading issues.
    """
    from sqlmodel import select
    from .. import models
    from ..core.extension_loader import get_extension_loader
    
    # Get all extensions from DB
    stmt = select(models.Extension)
    result = await session.exec(stmt)
    db_extensions = {ext.slug: ext for ext in result.all()}
    
    # Get loaded extensions from memory
    try:
        loader = get_extension_loader()
        loaded_slugs = set(loader.list_loaded_extensions())
    except RuntimeError:
        loaded_slugs = set()
    
    # Build status response
    status_list = []
    for slug, ext in db_extensions.items():
        status_list.append({
            "slug": slug,
            "name": ext.name,
            "version": ext.version,
            "is_active_in_db": ext.is_active,
            "is_loaded_in_memory": slug in loaded_slugs,
            "status": "active" if (ext.is_active and slug in loaded_slugs) else 
                     "disabled" if not ext.is_active else
                     "pending_restart" if ext.is_active and slug not in loaded_slugs else
                     "error"
        })
    
    return {
        "extensions": status_list,
        "total_in_db": len(db_extensions),
        "total_loaded": len(loaded_slugs),
        "active_count": sum(1 for s in status_list if s["status"] == "active"),
        "disabled_count": sum(1 for s in status_list if s["status"] == "disabled")
    }


@router.get("/{slug}/dependencies", status_code=status.HTTP_200_OK)
async def get_extension_dependencies(
    slug: str,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Get dependency information for an extension.
    
    Shows:
    - Required core version
    - Required extensions
    - Required Python packages
    - Validation status
    """
    from ..core.extension_loader import get_extension_loader
    from ..core.dependency_validator import DependencyValidator
    from .. import __version__ as LIFELOG_VERSION
    
    # Get extension from loader
    try:
        loader = get_extension_loader()
        ext_pkg = loader.get_extension(slug)
        
        if not ext_pkg:
            raise HTTPException(
                status_code=404,
                detail=f"Extension '{slug}' not loaded in memory"
            )
        
        manifest = ext_pkg.manifest
        
        # Build dependency tree
        validator = DependencyValidator(LIFELOG_VERSION)
        validator.set_installed_extensions({
            s: p.manifest.version
            for s, p in loader.loaded_extensions.items()
        })
        
        dep_tree = validator.get_dependency_tree(manifest)
        
        # Validate dependencies
        is_valid, errors = validator.validate_manifest(manifest, skip_python_packages=False)
        
        return {
            "slug": slug,
            "version": manifest.version,
            "dependencies": {
                "core": dep_tree["core"],
                "extensions": dep_tree["extensions"],
                "python_packages": dep_tree["python_packages"]
            },
            "validation": {
                "is_valid": is_valid,
                "errors": errors
            },
            "current_core_version": LIFELOG_VERSION
        }
        
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail="Extension loader not initialized"
        )


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


@router.get("/{slug}/config", status_code=status.HTTP_200_OK)
async def get_extension_config(
    slug: str,
    mask_secrets: bool = True,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Get extension configuration.
    
    Args:
        slug: Extension slug
        mask_secrets: Whether to mask secret fields (default: True)
        
    Returns:
        Extension configuration with optional secret masking
    """
    config = await ExtensionService.get_extension_config(session, slug, mask_secrets=mask_secrets)
    
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extension '{slug}' not found"
        )
    
    return {"slug": slug, "config": config}


@router.put("/{slug}/config", status_code=status.HTTP_200_OK)
async def update_extension_config(
    slug: str,
    config_update: schemas.ExtensionConfigUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Update extension configuration.
    
    Args:
        slug: Extension slug
        config_update: Configuration fields to update
        
    Returns:
        Updated extension configuration
    """
    try:
        extension = await ExtensionService.update_extension_config(
            session, 
            slug, 
            config_update.config,
            validate=True
        )
        
        return {
            "message": f"Configuration updated for extension '{slug}'",
            "slug": slug,
            "config": extension.config
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{slug}/config/reset", status_code=status.HTTP_200_OK)
async def reset_extension_config(
    slug: str,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Reset extension configuration to defaults from schema.
    
    Args:
        slug: Extension slug
        
    Returns:
        Reset configuration
    """
    try:
        extension = await ExtensionService.reset_extension_config(session, slug)
        
        return {
            "message": f"Configuration reset to defaults for extension '{slug}'",
            "slug": slug,
            "config": extension.config
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/{slug}/config/schema", status_code=status.HTTP_200_OK)
async def get_extension_config_schema(
    slug: str,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Get extension configuration schema.
    
    Args:
        slug: Extension slug
        
    Returns:
        JSON Schema for extension configuration
    """
    extension = await ExtensionService.get_extension(session, slug)
    
    if not extension:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extension '{slug}' not found"
        )
    
    return {
        "slug": slug,
        "config_schema": extension.config_schema
    }


@router.delete("/{slug}", status_code=status.HTTP_200_OK)
async def uninstall_extension(
    slug: str,
    delete_data: bool = False,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Uninstall an extension from the system.
    
    This endpoint:
    1. Calls the on_uninstall lifecycle hook (if extension is loaded)
    2. Optionally deletes extension-related data based on delete_data parameter
    3. Removes the extension record from the database
    
    Args:
        slug: Extension slug to uninstall
        delete_data: If True, also delete extension-created data (actors, event types, etc.)
                     If False, orphan the data (keeps data but removes extension reference)
        
    **Warning**: This operation is irreversible. The extension will need to be 
    reinstalled from scratch if you want to use it again.
    
    **Data Deletion**:
    - delete_data=False (default): Removes extension metadata but keeps actors, event types.
      Existing events and raw logs are preserved.
    - delete_data=True: Removes extension metadata AND all actors, event types, prompt templates.
      Events and raw logs are still preserved but may have orphaned references.
    """
    try:
        success = await ExtensionService.uninstall_extension(
            session,
            slug,
            delete_data=delete_data
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Extension '{slug}' not found"
            )
        
        return {
            "message": f"Extension '{slug}' uninstalled successfully",
            "slug": slug,
            "data_deleted": delete_data,
            "warning": "This extension has been removed from the database. "
                      "Reload the server to fully unload extension code." if not delete_data else None
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{slug}/lifecycle-logs", status_code=status.HTTP_200_OK)
async def get_extension_lifecycle_logs(
    slug: str,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Get lifecycle hook execution history for an extension.
    
    Shows when lifecycle hooks (on_install, on_activate, on_upgrade, on_deactivate, on_uninstall)
    were executed, whether they succeeded, and how long they took.
    
    Useful for debugging extension lifecycle issues.
    """
    from sqlmodel import select
    from .. import models
    
    # Get extension
    extension = await ExtensionService.get_extension(session, slug)
    if not extension:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extension '{slug}' not found"
        )
    
    # Get lifecycle logs
    stmt = (
        select(models.ExtensionLifecycleLog)
        .where(models.ExtensionLifecycleLog.extension_id == extension.id)
        .order_by(models.ExtensionLifecycleLog.executed_at.desc())  # type: ignore[attr-defined]
        .limit(limit)
    )
    result = await session.exec(stmt)
    logs = list(result.all())
    
    return {
        "slug": slug,
        "total_logs": len(logs),
        "logs": [
            {
                "hook_name": log.hook_name,
                "executed_at": log.executed_at.isoformat(),
                "success": log.success,
                "error_message": log.error_message,
                "execution_time_ms": log.execution_time_ms,
                "context": log.context
            }
            for log in logs
        ]
    }



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
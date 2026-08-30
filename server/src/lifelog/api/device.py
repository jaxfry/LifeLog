from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from typing import Optional, Dict, Any, List
import io
import os
import zipfile
import hashlib
from pathlib import Path

from ..dependencies import get_session
from ..auth import device_auth_dependency
from .. import models
from ..core.config import settings

router = APIRouter(prefix="/device", tags=["Device"])


class DeviceInstalledExtensionResponse(models.SQLModel, table=False):  # type: ignore[misc]
    slug: str  # type: ignore[assignment]
    name: str  # type: ignore[assignment]
    version: str  # type: ignore[assignment]
    is_active: bool  # type: ignore[assignment]
    client_manifest: Optional[Dict[str, Any]] = None  # type: ignore[assignment]


@router.get("/extensions")
async def list_extensions_for_device(
    platform: str = Query(..., description="Platform identifier: macos|windows|linux|ios|android"),
    session: AsyncSession = Depends(get_session),
    device = Depends(device_auth_dependency),
):
    """
    Return active extensions with client-side manifests filtered by platform.

    - Auth: Device API key (X-Device-Key)
    - Response: [{ slug, name, version, is_active, client_manifest }]
      where client_manifest is the subset for the requested platform.
    """
    # Fetch all active extensions
    result = await session.exec(select(models.Extension).where(models.Extension.is_active == True))
    exts: List[models.Extension] = list(result.all())

    items: List[Dict[str, Any]] = []
    for ext in exts:
        cfg = ext.config or {}
        client_manifest = cfg.get("client_side") or {}
        # Filter platforms
        platforms = client_manifest.get("platforms", {}) if isinstance(client_manifest, dict) else {}
        plat_cfg = platforms.get(platform)
        items.append({
            "slug": ext.slug,
            "name": ext.name,
            "version": ext.version,
            "is_active": bool(ext.is_active),
            "client_manifest": {"platforms": {platform: plat_cfg}} if plat_cfg else None,
        })

    return items


def _zip_dir_to_bytes(src_dir: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(src_dir):
            for f in files:
                full_path = Path(root) / f
                # write relative to src_dir
                rel = full_path.relative_to(src_dir)
                zf.write(full_path, arcname=str(rel))
    buf.seek(0)
    return buf.read()


@router.get("/extensions/{slug}/{version}/package")
async def download_extension_package(
    slug: str,
    version: str,
    session: AsyncSession = Depends(get_session),
    device = Depends(device_auth_dependency),
):
    """
    Stream a zip package of the installed extension version from the server's store.

    The server stores extracted assets in EXTENSIONS_STORE_PATH as <slug>-<version>/. We
    repackage that directory as a zip for client distribution and include an SHA-256 checksum
    header (X-Checksum-SHA256) for integrity verification on clients.
    """
    # Verify extension exists and version matches
    ext = (await session.exec(select(models.Extension).where(models.Extension.slug == slug))).one_or_none()
    if not ext:
        raise HTTPException(status_code=404, detail="Extension not found")
    if ext.version != version:
        # Allow download of any stored version if present on disk even if DB points elsewhere
        pass

    store_root = Path(settings.EXTENSIONS_STORE_PATH)
    src_dir = store_root / f"{slug}-{version}"
    if not src_dir.exists() or not src_dir.is_dir():
        # Fallback for local dev: use dynamic extensions path if manifest version matches
        dyn_dir = Path(settings.EXTENSIONS_PATH) / slug
        mf = dyn_dir / "manifest.json"
        if dyn_dir.exists() and mf.exists():
            try:
                import json
                mf_json = json.loads(mf.read_text())
                mf_version = str(mf_json.get("version", ""))
                if mf_version == version:
                    src_dir = dyn_dir
                else:
                    raise HTTPException(status_code=404, detail="Extension version mismatch in dynamic folder")
            except Exception:
                raise HTTPException(status_code=404, detail="Could not read manifest for dynamic extension fallback")
        else:
            raise HTTPException(status_code=404, detail="Requested version assets not found in store")

    data = _zip_dir_to_bytes(src_dir)
    checksum = hashlib.sha256(data).hexdigest()

    async def streamer():
        yield data

    resp = StreamingResponse(streamer(), media_type="application/zip")
    resp.headers["Content-Disposition"] = f"attachment; filename={slug}-{version}.zip"
    resp.headers["X-Checksum-SHA256"] = checksum
    return resp


@router.get("/config")
async def get_device_config(
    session: AsyncSession = Depends(get_session),
    device = Depends(device_auth_dependency),
):
    """
    Return the device's client configuration blob (for collectors and local agent settings).
    Shape is free-form JSON; recommended structure:
    {
      "agent": { ... },
      "collectors": { "<extension_slug>": { "<collector_slug>": { ...settings... } } }
    }
    """
    dev: models.Device = await session.get(models.Device, device.id)  # type: ignore[arg-type]
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")
    return dev.client_metadata or {}


@router.put("/config")
async def update_device_config(
    payload: Dict[str, Any],
    session: AsyncSession = Depends(get_session),
    device = Depends(device_auth_dependency),
):
    """
    Merge the provided JSON into the device's client_metadata atomically.
    Shallow merge at top level keys (agent, collectors, etc.).
    """
    dev: models.Device = await session.get(models.Device, device.id)  # type: ignore[arg-type]
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found")

    current = dev.client_metadata or {}
    # shallow merge top-level
    for k, v in payload.items():
        if isinstance(current.get(k), dict) and isinstance(v, dict):
            current[k] = {**current[k], **v}
        else:
            current[k] = v
    dev.client_metadata = current
    session.add(dev)
    await session.commit()
    await session.refresh(dev)
    return dev.client_metadata


@router.get("/cursor/{source_actor_slug}/{cursor_key}")
async def get_sync_cursor(
    source_actor_slug: str,
    cursor_key: str,
    session: AsyncSession = Depends(get_session),
    device = Depends(device_auth_dependency),
):
    """
    Get the sync cursor for a specific source actor and cursor key.
    Returns the cursor value or 404 if not found.
    
    This allows agents to resume from their last successful sync point.
    """
    # Find source actor
    actor_stmt = select(models.Actor).where(models.Actor.slug == source_actor_slug)
    actor = (await session.exec(actor_stmt)).first()
    if not actor or actor.id is None:
        raise HTTPException(status_code=404, detail=f"Source actor '{source_actor_slug}' not found")
    
    # Find cursor
    cursor_stmt = (
        select(models.SyncCursor)
        .where(models.SyncCursor.device_id == device.id)
        .where(models.SyncCursor.source_actor_id == actor.id)
        .where(models.SyncCursor.cursor_key == cursor_key)
    )
    cursor = (await session.exec(cursor_stmt)).first()
    
    if not cursor:
        raise HTTPException(status_code=404, detail="Cursor not found")
    
    return {
        "cursor_key": cursor.cursor_key,
        "cursor_value": cursor.cursor_value,
        "last_updated": cursor.last_updated.isoformat()
    }


@router.put("/cursor/{source_actor_slug}/{cursor_key}")
async def update_sync_cursor(
    source_actor_slug: str,
    cursor_key: str,
    payload: Dict[str, str],
    session: AsyncSession = Depends(get_session),
    device = Depends(device_auth_dependency),
):
    """
    Update or create a sync cursor for a specific source actor and cursor key.
    
    Payload should contain:
    {
        "cursor_value": "2024-11-16T12:34:56Z"  # or any string value
    }
    
    This allows agents to checkpoint their progress server-side.
    """
    cursor_value = payload.get("cursor_value")
    if not cursor_value:
        raise HTTPException(status_code=400, detail="cursor_value is required")
    
    # Find source actor
    actor_stmt = select(models.Actor).where(models.Actor.slug == source_actor_slug)
    actor = (await session.exec(actor_stmt)).first()
    if not actor or actor.id is None:
        raise HTTPException(status_code=404, detail=f"Source actor '{source_actor_slug}' not found")
    
    # Use PostgreSQL UPSERT for atomic cursor update
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from datetime import datetime, timezone
    
    values = {
        "device_id": device.id,
        "source_actor_id": actor.id,
        "cursor_key": cursor_key,
        "cursor_value": cursor_value,
        "last_updated": datetime.now(timezone.utc)
    }
    
    stmt = pg_insert(models.SyncCursor).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=['device_id', 'source_actor_id', 'cursor_key'],
        set_={
            "cursor_value": cursor_value,
            "last_updated": datetime.now(timezone.utc)
        }
    )
    
    await session.execute(stmt)
    await session.commit()
    
    # Fetch the updated cursor
    cursor_stmt = (
        select(models.SyncCursor)
        .where(models.SyncCursor.device_id == device.id)
        .where(models.SyncCursor.source_actor_id == actor.id)
        .where(models.SyncCursor.cursor_key == cursor_key)
    )
    cursor = (await session.exec(cursor_stmt)).first()
    
    return {
        "cursor_key": cursor.cursor_key,
        "cursor_value": cursor.cursor_value,
        "last_updated": cursor.last_updated.isoformat()
    }

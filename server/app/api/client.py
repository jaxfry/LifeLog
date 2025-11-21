import os
import zipfile
import io
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.core.db import get_session
from app.core.logger import get_logger
from app.models.config import Extension

logger = get_logger(__name__)
router = APIRouter()

EXTENSIONS_DIR = "extensions"  # Relative to server root

@router.get("/client/extensions", response_model=List[Extension])
async def list_client_extensions(
    session: AsyncSession = Depends(get_session)
):
    # In a real app, we might filter by device permissions.
    # For now, return all active extensions.
    
    # First, ensure we have the extensions in the DB that match the filesystem
    # This is a bit of a hack for this stage of development to auto-register extensions
    # In production, this would be a separate admin process
    await _sync_extensions_db(session)
    
    statement = select(Extension).where(Extension.is_active == True)
    result = await session.execute(statement)
    return result.scalars().all()

@router.get("/client/download/{extension_id}")
async def download_extension(
    extension_id: str,
    session: AsyncSession = Depends(get_session)
):
    # Verify extension exists
    extension = await session.get(Extension, extension_id)
    if not extension:
        raise HTTPException(status_code=404, detail="Extension not found")
    
    ext_path = os.path.join(EXTENSIONS_DIR, extension_id)
    if not os.path.exists(ext_path):
        raise HTTPException(status_code=404, detail="Extension files not found on server")
    
    # Create a zip file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(ext_path):
            for file in files:
                # Don't include __pycache__
                if "__pycache__" in root:
                    continue
                
                file_path = os.path.join(root, file)
                # Ensure we are getting the path relative to the extension folder
                archive_name = os.path.relpath(file_path, ext_path)
                logger.debug(f"Zipping {file_path} as {archive_name}")
                zip_file.write(file_path, archive_name)
    
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={extension_id}.zip"}
    )

async def _sync_extensions_db(session: AsyncSession):
    """
    Helper to populate DB with extensions found on disk.
    Also deactivates extensions in DB that are not found on disk.
    """
    if not os.path.exists(EXTENSIONS_DIR):
        return

    found_extensions = set()

    # 1. Add/Update from Disk
    for item in os.listdir(EXTENSIONS_DIR):
        item_path = os.path.join(EXTENSIONS_DIR, item)
        if os.path.isdir(item_path):
            manifest_path = os.path.join(item_path, "manifest.json")
            if os.path.exists(manifest_path):
                import json
                try:
                    with open(manifest_path, "r") as f:
                        manifest = json.load(f)
                    
                    ext_id = manifest.get("id")
                    if ext_id == item:
                        found_extensions.add(ext_id)
                        # Check if exists
                        existing = await session.get(Extension, ext_id)
                        if not existing:
                            new_ext = Extension(
                                id=ext_id,
                                version=manifest.get("version", "0.0.1"),
                                config=manifest,
                                is_active=True
                            )
                            session.add(new_ext)
                            await session.commit()
                        else:
                            # Update version if changed
                            current_version = manifest.get("version", "0.0.1")
                            # Also ensure it is active if it was previously inactive
                            if existing.version != current_version or not existing.is_active:
                                existing.version = current_version
                                existing.config = manifest
                                existing.is_active = True
                                session.add(existing)
                                await session.commit()
                                logger.info(f"Updated/Reactivated extension {ext_id}")
                except Exception as e:
                    logger.error(f"Error loading manifest for {item}: {e}")

    # 2. Deactivate missing extensions
    statement = select(Extension).where(Extension.is_active == True)
    result = await session.execute(statement)
    active_extensions = result.scalars().all()

    for ext in active_extensions:
        if ext.id not in found_extensions:
            logger.info(f"Deactivating extension {ext.id} (not found on disk)")
            ext.is_active = False
            session.add(ext)
    
    await session.commit()

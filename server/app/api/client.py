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
from app.models.config import Extension, Device
from app.api.deps import verify_api_key
from app.core.extension_utils import sync_extensions_db, EXTENSIONS_DIR

logger = get_logger(__name__)
router = APIRouter()

@router.get("/client/extensions", response_model=List[Extension])
async def list_client_extensions(
    session: AsyncSession = Depends(get_session),
    device: Device = Depends(verify_api_key)
):
    # In a real app, we might filter by device permissions.
    # For now, return all active extensions.
    
    statement = select(Extension).where(Extension.is_active == True)
    result = await session.execute(statement)
    return result.scalars().all()

@router.get("/client/download/{extension_id}")
async def download_extension(
    extension_id: str,
    session: AsyncSession = Depends(get_session),
    device: Device = Depends(verify_api_key)
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

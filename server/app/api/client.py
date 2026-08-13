import io
import os
import zipfile

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_session
from app.core.dependencies import verify_device
from app.core.extension_utils import EXTENSIONS_DIR
from app.core.logger import get_logger
from app.models.auth import Device
from app.models.config import Extension

logger = get_logger(__name__)
router = APIRouter()


@router.get("/client/extensions", response_model=list[Extension])
async def list_client_extensions(
    db_session: AsyncSession = Depends(get_session),
    device: Device = Depends(verify_device),
):
    result = await db_session.execute(
        select(Extension).where(Extension.is_active == True)
    )
    return result.scalars().all()


@router.get("/client/download/{extension_id}")
async def download_extension(
    extension_id: str,
    db_session: AsyncSession = Depends(get_session),
    device: Device = Depends(verify_device),
):
    extension = await db_session.get(Extension, extension_id)
    if not extension:
        raise HTTPException(status_code=404, detail="Extension not found")

    ext_path = os.path.join(EXTENSIONS_DIR, extension_id)
    if not os.path.exists(ext_path):
        raise HTTPException(status_code=404, detail="Extension files not found on server")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(ext_path):
            for fname in files:
                if "__pycache__" in root:
                    continue
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, ext_path)
                zf.write(fpath, arcname)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{extension_id}.zip"'},
    )

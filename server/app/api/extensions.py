import os
import shutil
import zipfile
import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.core.db import get_session
from app.core.logger import get_logger
from app.models.config import Extension, User
from app.api.deps import get_current_user, get_current_superuser
from app.core.extension_utils import sync_extensions_db, EXTENSIONS_DIR

logger = get_logger(__name__)
router = APIRouter()

@router.get("/extensions", response_model=List[Extension])
async def list_extensions(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    List all extensions (for web UI).
    """
    await sync_extensions_db(session)
    
    statement = select(Extension).order_by(Extension.id)
    result = await session.execute(statement)
    return result.scalars().all()

@router.post("/extensions/upload")
async def upload_extension(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser)
):
    """
    Upload and install a new extension.
    """
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only .zip files are allowed")

    # Save temporary file
    temp_path = f"temp_{file.filename}"
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Validate zip content
        with zipfile.ZipFile(temp_path, 'r') as zip_ref:
            # Check for manifest.json
            extract_subdir = None
            
            if "manifest.json" in zip_ref.namelist():
                pass # Root level
            else:
                # Check for single top-level directory
                top_level_dirs = {name.split('/')[0] for name in zip_ref.namelist() if '/' in name}
                if len(top_level_dirs) == 1:
                    subdir = list(top_level_dirs)[0]
                    if f"{subdir}/manifest.json" in zip_ref.namelist():
                        extract_subdir = subdir
                    else:
                         raise HTTPException(status_code=400, detail="manifest.json not found in zip")
                else:
                     raise HTTPException(status_code=400, detail="manifest.json not found in zip root")

            # Read manifest
            manifest_data = None
            if extract_subdir:
                with zip_ref.open(f"{extract_subdir}/manifest.json") as f:
                    manifest_data = json.load(f)
            else:
                with zip_ref.open("manifest.json") as f:
                    manifest_data = json.load(f)
            
            ext_id = manifest_data.get("id")
            if not ext_id:
                raise HTTPException(status_code=400, detail="Extension ID not found in manifest.json")
            
            target_dir = os.path.join(EXTENSIONS_DIR, ext_id)
            
            # Remove existing if any
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            
            os.makedirs(target_dir, exist_ok=True)
            
            # Extract files
            for member in zip_ref.infolist():
                if extract_subdir and member.filename.startswith(f"{extract_subdir}/"):
                    target_name = member.filename[len(extract_subdir)+1:]
                    if not target_name: continue
                    target_path = os.path.join(target_dir, target_name)
                elif not extract_subdir:
                    target_path = os.path.join(target_dir, member.filename)
                else:
                    continue
                
                # Prevent path traversal
                if not os.path.abspath(target_path).startswith(os.path.abspath(target_dir)):
                    continue

                if member.is_dir():
                    os.makedirs(target_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with open(target_path, "wb") as target_file:
                        with zip_ref.open(member) as source_file:
                            shutil.copyfileobj(source_file, target_file)

    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid zip file")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid manifest.json")
    except Exception as e:
        logger.error(f"Error uploading extension: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    # Sync DB
    await sync_extensions_db(session)
    
    return {"message": f"Extension {ext_id} installed successfully"}

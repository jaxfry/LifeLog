import json
import os
import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_session
from app.core.dependencies import get_current_superuser, get_current_user
from app.core.extension_utils import EXTENSIONS_DIR, sync_extensions_db
from app.core.logger import get_logger
from app.loader.contracts import validate_extension_manifest
from app.models.auth import User
from app.models.config import Extension
from app.services.source_secrets import redact_config

logger = get_logger(__name__)
router = APIRouter()


@router.get("/extensions")
async def list_extensions(
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    await sync_extensions_db(db_session)
    result = await db_session.execute(select(Extension).order_by(Extension.id))
    extensions = result.scalars().all()
    return [
        {
            **extension.model_dump(),
            "config": redact_config(extension.config or {}),
        }
        for extension in extensions
    ]


@router.post("/extensions/upload")
async def upload_extension(
    file: UploadFile = File(...),
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser),
):
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are allowed")

    temp_path = f"temp_{file.filename}"
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        with zipfile.ZipFile(temp_path, "r") as zf:
            extract_subdir = None
            if "manifest.json" in zf.namelist():
                pass
            else:
                top_dirs = {n.split("/")[0] for n in zf.namelist() if "/" in n}
                if len(top_dirs) == 1:
                    sd = list(top_dirs)[0]
                    if f"{sd}/manifest.json" in zf.namelist():
                        extract_subdir = sd

            manifest_data = None
            if extract_subdir:
                with zf.open(f"{extract_subdir}/manifest.json") as f:
                    manifest_data = json.load(f)
            else:
                with zf.open("manifest.json") as f:
                    manifest_data = json.load(f)

            parsed_manifest = validate_extension_manifest(manifest_data)
            ext_id = parsed_manifest.id

            target_dir = os.path.join(EXTENSIONS_DIR, ext_id)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            os.makedirs(target_dir, exist_ok=True)

            for member in zf.infolist():
                if extract_subdir and member.filename.startswith(f"{extract_subdir}/"):
                    target_name = member.filename[len(extract_subdir) + 1:]
                    if not target_name:
                        continue
                    target_path = os.path.join(target_dir, target_name)
                elif not extract_subdir:
                    target_path = os.path.join(target_dir, member.filename)
                else:
                    continue

                resolved_target = Path(target_path).resolve()
                if not resolved_target.is_relative_to(Path(target_dir).resolve()):
                    raise HTTPException(status_code=400, detail="Extension archive contains an unsafe path")
                if member.is_dir() is False and (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise HTTPException(status_code=400, detail="Extension archive may not contain symbolic links")

                if member.is_dir():
                    os.makedirs(target_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with zf.open(member) as src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)

    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid zip file")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid manifest.json")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid extension manifest: {e}")
    except Exception as e:
        logger.exception("Upload error")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    await sync_extensions_db(db_session)
    return {"message": f"Extension {ext_id} installed successfully"}

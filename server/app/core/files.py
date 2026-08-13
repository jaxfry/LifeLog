import hashlib
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.file_processing import extract_metadata
from app.core.logger import get_logger
from app.models.files import FileAttachment

logger = get_logger(__name__)

UPLOAD_DIR = Path("storage/uploads")

def get_storage_path(content_hash: str) -> Path:
    """
    Returns the absolute path for a given content hash.
    Structure: storage/uploads/ab/cd/abcdef1234...
    """
    # Use first 2 chars for first level, next 2 for second level
    # This avoids having too many files in one directory
    return UPLOAD_DIR / content_hash[:2] / content_hash[2:4] / content_hash

async def calculate_hash(file: UploadFile) -> str:
    """
    Calculates SHA-256 hash of an UploadFile.
    Resets cursor to 0 after reading.
    """
    sha256 = hashlib.sha256()
    size_bytes = 0
    max_bytes = settings.MAX_ARTIFACT_SIZE_MB * 1024 * 1024
    await file.seek(0)
    while chunk := await file.read(8192):
        size_bytes += len(chunk)
        if size_bytes > max_bytes:
            await file.seek(0)
            raise ValueError(f"Artifact exceeds the {settings.MAX_ARTIFACT_SIZE_MB} MB limit")
        sha256.update(chunk)
    await file.seek(0)
    return sha256.hexdigest()

async def save_file(file: UploadFile) -> tuple[str, int, str]:
    """
    Saves an UploadFile to the content-addressable storage.
    Returns (content_hash, size_bytes, stored_path_relative).
    """
    content_hash = await calculate_hash(file)
    storage_path = get_storage_path(content_hash)

    # Ensure UPLOAD_DIR exists
    if not UPLOAD_DIR.exists():
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    relative_path = str(storage_path.relative_to(UPLOAD_DIR))

    # Create directories if they don't exist
    storage_path.parent.mkdir(parents=True, exist_ok=True)

    # If file already exists, we don't need to write it again (deduplication)
    if storage_path.exists():
        logger.info(f"File with hash {content_hash} already exists. Skipping write.")
        # Get size from existing file
        size_bytes = storage_path.stat().st_size
        return content_hash, size_bytes, relative_path

    # Write file to disk
    size_bytes = 0
    with open(storage_path, "wb") as f:
        while chunk := await file.read(8192):
            f.write(chunk)
            size_bytes += len(chunk)

    await file.seek(0) # Reset for any further usage
    logger.info(f"Saved file {content_hash} to {storage_path}")

    return content_hash, size_bytes, relative_path

async def create_attachment(
    session: AsyncSession,
    file: UploadFile,
    filename: str | None = None,
    mime_type: str | None = None,
    category: str | None = None,
    tags: list[str] = [],
    event_id: UUID | None = None,
    timeline_id: UUID | None = None,
    description: str | None = None,
    source_extension_id: str | None = None,
) -> FileAttachment:
    """
    High-level function to handle upload and DB record creation.
    """
    if source_extension_id is not None:
        from app.models.config import Extension

        extension = await session.get(Extension, source_extension_id)
        if extension is None or not extension.is_active:
            raise ValueError("source_extension_id must identify an active extension")
        if "artifact_source" not in (extension.config or {}).get("capabilities", []):
            raise ValueError("source extension does not declare the artifact_source capability")

    content_hash, size_bytes, stored_path = await save_file(file)

    # Extract metadata
    full_path = UPLOAD_DIR / stored_path
    final_mime_type = mime_type or file.content_type or "application/octet-stream"
    technical_metadata = await extract_metadata(full_path, final_mime_type)

    attachment = FileAttachment(
        filename=filename or file.filename or "unknown",
        mime_type=final_mime_type,
        size_bytes=size_bytes,
        content_hash=content_hash,
        stored_path=stored_path,
        category=category,
        tags=tags,
        event_id=event_id,
        timeline_id=timeline_id,
        description=description,
        source_extension_id=source_extension_id,
        technical_metadata=technical_metadata
    )

    session.add(attachment)
    await session.flush()

    return attachment

import json
import os
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logger import get_logger
from app.loader.contracts import validate_extension_manifest
from app.models.config import Extension

logger = get_logger(__name__)
EXTENSIONS_DIR = "extensions"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def sync_extensions_db(session: AsyncSession):
    """
    Helper to populate DB with extensions found on disk.
    Also archives extensions in DB that are not found on disk
    (archived extensions keep their data but stop processing).
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
                try:
                    with open(manifest_path) as f:
                        manifest = json.load(f)

                    parsed_manifest = validate_extension_manifest(manifest)
                    ext_id = parsed_manifest.id
                    # If the folder name matches the ID, or we just trust the manifest ID
                    # Usually good practice to enforce folder name == ID, but let's trust manifest ID
                    if ext_id:
                        found_extensions.add(ext_id)
                        # Check if exists
                        existing = await session.get(Extension, ext_id)
                        if not existing:
                            new_ext = Extension(
                                id=ext_id,
                                version=parsed_manifest.version,
                                api_version=parsed_manifest.api_version,
                                config=parsed_manifest.model_dump(mode="json"),
                                scheduler_cron=parsed_manifest.scheduler_cron,
                                is_active=True,
                            )
                            session.add(new_ext)
                            # We commit per item or at the end?
                            # If we commit at the end, we might have issues when adding the same ID twice.
                        else:
                            current_version = parsed_manifest.version
                            existing.version = current_version
                            existing.api_version = parsed_manifest.api_version
                            existing.config = parsed_manifest.model_dump(mode="json")
                            existing.scheduler_cron = parsed_manifest.scheduler_cron
                            existing.is_active = True
                            existing.archived_at = None
                            session.add(existing)
                            logger.info("Synced extension %s", ext_id)
                except Exception as e:
                    logger.error(f"Error loading manifest for {item}: {e}")

    # 2. Archive missing extensions (keep their data, stop processing)
    statement = select(Extension).where(Extension.is_active == True)
    result = await session.execute(statement)
    active_extensions = result.scalars().all()

    for ext in active_extensions:
        if ext.id not in found_extensions:
            logger.info(f"Archiving extension {ext.id} (not found on disk)")
            ext.is_active = False
            if ext.archived_at is None:
                ext.archived_at = _utcnow()
            session.add(ext)

    await session.commit()

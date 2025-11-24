import os
import json
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.config import Extension
from app.core.logger import get_logger

logger = get_logger(__name__)
EXTENSIONS_DIR = "extensions"

async def sync_extensions_db(session: AsyncSession):
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
                try:
                    with open(manifest_path, "r") as f:
                        manifest = json.load(f)
                    
                    ext_id = manifest.get("id")
                    # If the folder name matches the ID, or we just trust the manifest ID
                    # Usually good practice to enforce folder name == ID, but let's trust manifest ID
                    if ext_id:
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
                            # We commit per item or at the end? 
                            # If we commit at the end, we might have issues if we try to add same ID twice (unlikely here)
                        else:
                            # Update version if changed
                            current_version = manifest.get("version", "0.0.1")
                            # Also ensure it is active if it was previously inactive
                            if existing.version != current_version or not existing.is_active:
                                existing.version = current_version
                                existing.config = manifest
                                existing.is_active = True
                                session.add(existing)
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

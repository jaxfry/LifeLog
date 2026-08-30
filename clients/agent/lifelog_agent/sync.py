from __future__ import annotations
import asyncio
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Dict, Any

import logging
from .http import DeviceClient
from .config import AgentConfig, CONFIG_DIR
from .collectors import CollectorSupervisor

EXT_CACHE = CONFIG_DIR / "extensions"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


logger = logging.getLogger(__name__)


async def sync_extensions(cfg: AgentConfig, client: DeviceClient, sup: CollectorSupervisor) -> None:
    _ensure_dir(EXT_CACHE)
    listing = await client.get_device_extensions(cfg.platform)
    for item in listing:
        try:
            slug = item.get("slug")
            version = item.get("version")
            cman = item.get("client_manifest") or {}
            plat = cman.get("platforms", {}).get(cfg.platform) or {}
            collectors = (plat.get("collectors") or []) if isinstance(plat, dict) else []
            if not slug or not version:
                continue
            # Ensure package present
            dest_dir = EXT_CACHE / f"{slug}-{version}"
            if not dest_dir.exists():
                data, header_checksum = await client.download_extension_package(slug, version)
                # Verify checksum
                if header_checksum and header_checksum != _sha256(data):
                    logger.warning(f"Checksum mismatch for extension {slug}@{version}; skipping")
                    continue
                # Extract
                import io
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    zf.extractall(dest_dir)
            # Ensure collectors running
            for coll in collectors:
                cslug = coll.get("slug")
                entry = coll.get("entrypoint")
                if not cslug or not entry:
                    continue
                entry_path = dest_dir / entry
                if entry_path.exists():
                    sup.ensure_running(slug, cslug, entry_path)
        except Exception as e:
            logger.warning(f"Failed to sync extension item {item.get('slug')}: {e}")
            continue

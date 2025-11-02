from __future__ import annotations
import httpx
from typing import Any, Dict, Optional

class DeviceClient:
    def __init__(self, base_url: str, device_key: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip('/')
        self.headers = {"X-Device-Key": device_key}
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=timeout,
            follow_redirects=True,
        )

    async def get_device_extensions(self, platform: str) -> list[dict]:
        r = await self._client.get(f"/api/v1/device/extensions", params={"platform": platform})
        r.raise_for_status()
        return r.json()

    async def download_extension_package(self, slug: str, version: str) -> tuple[bytes, str]:
        r = await self._client.get(f"/api/v1/device/extensions/{slug}/{version}/package")
        r.raise_for_status()
        checksum = r.headers.get("X-Checksum-SHA256", "")
        return r.content, checksum

    async def get_device_config(self) -> Dict[str, Any]:
        r = await self._client.get("/api/v1/device/config")
        r.raise_for_status()
        return r.json()

    async def update_device_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = await self._client.put("/api/v1/device/config", json=payload)
        r.raise_for_status()
        return r.json()

    async def ingest(self, source_actor_slug: str, data: Dict[str, Any]) -> Dict[str, Any]:
        # Ingestion uses X-Device-Key header as well
        r = await self._client.post(
            "/ingest/",
            json={"source_actor_slug": source_actor_slug, "data": data},
        )
        r.raise_for_status()
        return r.json()

    async def aclose(self):
        await self._client.aclose()

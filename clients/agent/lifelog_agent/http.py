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

    async def ingest(
        self, 
        source_actor_slug: str, 
        data: Dict[str, Any],
        external_id: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ingest data with optional idempotency support.
        
        Args:
            source_actor_slug: Source actor slug
            data: Raw data payload
            external_id: Optional external event ID for idempotency
            idempotency_key: Optional idempotency key
        """
        payload = {
            "source_actor_slug": source_actor_slug,
            "data": data
        }
        if external_id:
            payload["external_id"] = external_id
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key
            
        r = await self._client.post("/ingest/", json=payload)
        r.raise_for_status()
        return r.json()
    
    async def get_cursor(self, source_actor_slug: str, cursor_key: str) -> Optional[str]:
        """
        Get the current cursor value for a source actor.
        Returns None if cursor doesn't exist.
        """
        try:
            r = await self._client.get(
                f"/api/v1/device/cursor/{source_actor_slug}/{cursor_key}"
            )
            r.raise_for_status()
            data = r.json()
            return data.get("cursor_value")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    async def update_cursor(
        self, 
        source_actor_slug: str, 
        cursor_key: str, 
        cursor_value: str
    ) -> Dict[str, Any]:
        """
        Update the cursor value for a source actor.
        """
        r = await self._client.put(
            f"/api/v1/device/cursor/{source_actor_slug}/{cursor_key}",
            json={"cursor_value": cursor_value}
        )
        r.raise_for_status()
        return r.json()

    async def aclose(self):
        await self._client.aclose()

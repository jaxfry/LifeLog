import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import engine

@pytest.mark.asyncio
async def test_device_lifecycle():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Register Device
        response = await ac.post("/api/v1/devices", json={"name": "Lifecycle Device", "type": "test"})
        assert response.status_code == 201
        data = response.json()
        device_id = data["device_id"]
        api_key = data["api_key"]
        assert device_id
        assert api_key

        # 2. Get Device
        response = await ac.get(f"/api/v1/devices/{device_id}")
        assert response.status_code == 200
        device_data = response.json()
        assert device_data["id"] == device_id
        assert device_data["name"] == "Lifecycle Device"
        assert device_data["type"] == "test"
        assert "api_key_hash" not in device_data

        # 3. Update Device
        response = await ac.patch(f"/api/v1/devices/{device_id}", json={"name": "Updated Device"})
        assert response.status_code == 200
        updated_data = response.json()
        assert updated_data["name"] == "Updated Device"
        assert updated_data["type"] == "test" # Should remain unchanged

        # 4. Rotate Key
        response = await ac.post(f"/api/v1/devices/{device_id}/rotate-key")
        assert response.status_code == 200
        key_data = response.json()
        assert key_data["device_id"] == device_id
        assert key_data["api_key"] != api_key
        new_api_key = key_data["api_key"]

        # 5. Delete Device
        response = await ac.delete(f"/api/v1/devices/{device_id}")
        assert response.status_code == 204

        # 6. Verify Deletion
        response = await ac.get(f"/api/v1/devices/{device_id}")
        assert response.status_code == 404

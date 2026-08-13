import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_device_lifecycle(async_client: AsyncClient, mock_superuser):
    device_id = f"lifecycle-device-{uuid.uuid4().hex[:8]}"

    # 1. Register Device
    response = await async_client.post(
        "/api/v1/devices",
        json={"id": device_id, "name": "Lifecycle Device", "device_type": "test"},
    )
    assert response.status_code == 201
    data = response.json()
    api_key = data["api_key"]
    assert data["id"] == device_id
    assert api_key

    # 2. Get Device
    response = await async_client.get(f"/api/v1/devices/{device_id}")
    assert response.status_code == 200
    device_data = response.json()
    assert device_data["id"] == device_id
    assert device_data["name"] == "Lifecycle Device"
    assert device_data["device_type"] == "test"
    assert "api_key_hash" not in device_data

    # 3. Update Device
    response = await async_client.patch(f"/api/v1/devices/{device_id}", json={"name": "Updated Device"})
    assert response.status_code == 200
    updated_data = response.json()
    assert updated_data["name"] == "Updated Device"
    assert updated_data["device_type"] == "test"  # Should remain unchanged

    # 4. Rotate Key
    response = await async_client.post(f"/api/v1/devices/{device_id}/rotate-key")
    assert response.status_code == 200
    key_data = response.json()
    assert key_data["api_key"] != api_key

    # 5. Delete Device
    response = await async_client.delete(f"/api/v1/devices/{device_id}")
    assert response.status_code == 204

    # 6. Verify Deletion
    response = await async_client.get(f"/api/v1/devices/{device_id}")
    assert response.status_code == 404

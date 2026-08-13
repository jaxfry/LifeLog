import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_device_registration_and_listing(mock_superuser, async_client: AsyncClient):
    # Register a device
    device_id = f"test-device-{uuid.uuid4().hex[:8]}"
    response = await async_client.post(
        "/api/v1/devices",
        json={"id": device_id, "name": "Test Device", "device_type": "mobile"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == device_id
    assert "api_key" in data

    # List devices
    response = await async_client.get("/api/v1/devices")
    assert response.status_code == 200
    devices = response.json()
    assert len(devices) > 0
    found = False
    for d in devices:
        if d["id"] == device_id:
            assert d["name"] == "Test Device"
            assert d["device_type"] == "mobile"
            assert "api_key_hash" not in d
            found = True
            break
    assert found


@pytest.mark.asyncio
@pytest.mark.integration
async def test_read_apis_empty(async_client: AsyncClient):
    # Get logs (might be empty or have data from other tests, just check status)
    response = await async_client.get("/api/v1/logs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    # Get events
    response = await async_client.get("/api/v1/events")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    # Get sessions
    response = await async_client.get("/api/v1/sessions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_duplicate_device_id_conflict(mock_superuser, async_client: AsyncClient):
    device_id = f"dup-device-{uuid.uuid4().hex[:8]}"
    payload = {"id": device_id, "name": "First", "device_type": "desktop"}

    first = await async_client.post("/api/v1/devices", json=payload)
    assert first.status_code == 201

    second = await async_client.post("/api/v1/devices", json=payload)
    assert second.status_code == 409

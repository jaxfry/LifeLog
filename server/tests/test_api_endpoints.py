import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import engine
from app.models.config import Device
import uuid
import hashlib

@pytest_asyncio.fixture(autouse=True)
async def reset_engine():
    yield
    await engine.dispose()

@pytest.mark.asyncio
async def test_device_registration_and_listing():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Register a device
        response = await ac.post("/api/v1/devices", json={"name": "Test Device", "type": "mobile"})
        assert response.status_code == 201
        data = response.json()
        assert "device_id" in data
        assert "api_key" in data
        device_id = data["device_id"]

        # List devices
        response = await ac.get("/api/v1/devices")
        assert response.status_code == 200
        devices = response.json()
        assert len(devices) > 0
        found = False
        for d in devices:
            if d["id"] == device_id:
                assert d["name"] == "Test Device"
                assert d["type"] == "mobile"
                found = True
                break
        assert found

@pytest.mark.asyncio
async def test_read_apis_empty():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Get logs (might be empty or have data from other tests, just check status)
        response = await ac.get("/api/v1/logs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

        # Get events
        response = await ac.get("/api/v1/events")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

import uuid
from datetime import datetime

import pytest

from app.models.ingest import RawLog


@pytest.mark.asyncio
@pytest.mark.integration
async def test_timezone_flow(async_client, session, mock_superuser, mock_device_auth):
    # 1. Ingest a log with a client timezone
    payload = {
        "extension_id": "test-ext",
        "payload": {"test": "data"},
        "client_timezone": "America/New_York",
    }
    headers = {
        "X-API-Key": "dummy-key",  # Mock override will accept this
    }
    response = await async_client.post("/api/v1/ingest", json=payload, headers=headers)
    assert response.status_code == 201
    log_id = uuid.UUID(response.json()["id"])

    # 2. Verify RawLog stored the timezone
    log = await session.get(RawLog, log_id)
    assert log.client_timezone == "America/New_York"
    assert log.extension_id == "test-ext"

    # 3. Verify the time utility logic directly
    from app.core.utils.time import get_day_bounds_utc

    start, end = get_day_bounds_utc(datetime(2024, 1, 1), "-0500")
    assert start.hour == 5  # 00:00 EST is 05:00 UTC
    assert end.day == 2
    assert end.hour == 4  # 23:59 EST is 04:59 UTC next day


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ingest_without_timezone(async_client, session, mock_device_auth):
    response = await async_client.post(
        "/api/v1/ingest",
        json={"extension_id": "test-ext", "payload": {"x": 1}},
        headers={"X-API-Key": "dummy-key"},
    )
    assert response.status_code == 201
    log_id = uuid.UUID(response.json()["id"])

    log = await session.get(RawLog, log_id)
    assert log.client_timezone is None
    assert log.client_timestamp is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ingest_duplicate(async_client, session, mock_device_auth):
    payload = {"extension_id": "test-ext", "payload": {"dup": True}}
    headers = {"X-API-Key": "dummy-key"}

    first = await async_client.post("/api/v1/ingest", json=payload, headers=headers)
    assert first.status_code == 201

    second = await async_client.post("/api/v1/ingest", json=payload, headers=headers)
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert second.json()["id"] == first.json()["id"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ingest_requires_device_auth(async_client):
    response = await async_client.post(
        "/api/v1/ingest",
        json={"extension_id": "test-ext", "payload": {"x": 1}},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code in [401, 403]

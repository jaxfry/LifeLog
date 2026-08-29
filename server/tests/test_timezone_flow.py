import uuid
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.main import app
from app.models.ingest import RawLog
from app.workers.process import process_log


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
async def test_ingest_semantic_dedup_collapses_regenerated_ids(async_client, mock_device_auth):
    signal = {
        "id": "11111111-1111-1111-1111-111111111111",
        "type": "motion",
        "start_time": "2026-08-13T19:19:32Z",
        "end_time": None,
        "data": {"activity": "stationary", "confidence": "2", "source": "core_motion_activity"},
    }
    headers = {"X-API-Key": "dummy-key"}

    first = await async_client.post(
        "/api/v1/ingest",
        json={"extension_id": "com.lifelog.ios", "payload": signal},
        headers=headers,
    )
    assert first.status_code == 201

    # Same (type, start, end, data), only the client-generated id differs:
    # a re-buffered or live/backfill-overlapped write must collapse.
    signal["id"] = "22222222-2222-2222-2222-222222222222"
    second = await async_client.post(
        "/api/v1/ingest",
        json={"extension_id": "com.lifelog.ios", "payload": signal},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert second.json()["id"] == first.json()["id"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ingest_semantic_dedup_keeps_different_data(async_client, mock_device_auth):
    signal = {
        "id": "11111111-1111-1111-1111-111111111111",
        "type": "motion",
        "start_time": "2026-08-13T19:19:32Z",
        "end_time": None,
        "data": {"activity": "walking", "confidence": "2", "source": "core_motion_activity"},
    }
    headers = {"X-API-Key": "dummy-key"}
    first = await async_client.post(
        "/api/v1/ingest",
        json={"extension_id": "com.lifelog.ios", "payload": signal},
        headers=headers,
    )
    assert first.status_code == 201

    signal["id"] = "22222222-2222-2222-2222-222222222222"
    signal["data"]["activity"] = "running"
    second = await async_client.post(
        "/api/v1/ingest",
        json={"extension_id": "com.lifelog.ios", "payload": signal},
        headers=headers,
    )
    assert second.status_code == 201


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ingest_enqueues_normalization(async_client, mock_device_auth):
    pool = AsyncMock()
    app.state.arq_pool = pool
    try:
        response = await async_client.post(
            "/api/v1/ingest",
            json={"extension_id": "test-ext", "payload": {"queued": True}},
            headers={"X-API-Key": "dummy-key"},
        )
    finally:
        del app.state.arq_pool

    assert response.status_code == 201
    pool.enqueue_job.assert_awaited_once_with(
        "task_normalize_log", response.json()["id"]
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ingest_requires_device_auth(async_client):
    response = await async_client.post(
        "/api/v1/ingest",
        json={"extension_id": "test-ext", "payload": {"x": 1}},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_processing_uses_client_timezone_and_activity_duration(
    session, mock_device_auth
):
    from app.services.ingestion import ingest_log

    log, _ = await ingest_log(
        session,
        device_id="tz-device",
        extension_id="com.lifelog.aw",
        client_timezone="America/Vancouver",
        payload={
            "events": [
                {
                    "bucket_type": "currentwindow",
                    "bucket_id": "aw-watcher-window_mbp",
                    "timestamp": "2026-08-13T05:30:00Z",
                    "duration": 90.5,
                    "data": {"app": "Code", "title": "LifeLog"},
                }
            ]
        },
    )
    events = await process_log(session, log.id)

    assert len(events) == 1
    assert events[0].logical_date == "2026-08-12"
    assert (events[0].end_time - events[0].start_time).total_seconds() == 90.5

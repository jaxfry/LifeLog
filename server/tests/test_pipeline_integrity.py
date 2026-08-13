import os
import shutil
import uuid

import pytest
from sqlalchemy import select

from app.models.ingest import Event, RawLog

# Configuration
EXTENSIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../extensions"))

# Skip these tests when using a separate test database since the worker
# uses its own database connection that won't point to the test DB
pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_DATABASE_URL") is not None,
    reason="Pipeline integrity tests require worker to share the same database connection. "
           "Run without TEST_DATABASE_URL for full integration testing."
)

# Import only when not skipped
from app.workers.main import task_normalize_log


def create_extension(name, code):
    path = os.path.join(EXTENSIONS_DIR, name)
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "processor.py"), "w") as f:
        f.write(code)
    with open(os.path.join(path, "manifest.json"), "w") as f:
        f.write('{"name": "' + name + '"}')
    return path


def remove_extension(name):
    path = os.path.join(EXTENSIONS_DIR, name)
    if os.path.exists(path):
        shutil.rmtree(path)


async def _ingest(async_client, extension_id, payload):
    response = await async_client.post(
        "/api/v1/ingest",
        json={"extension_id": extension_id, "payload": payload},
        headers={"X-API-Key": "dummy-key"},
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scenario_1_end_to_end(async_client, session, mock_device_auth):
    """
    Scenario 1: The Full End-to-End Flow
    """
    ext_name = "com.lifelog.test"
    code = """
from typing import Dict, Any, List
def normalize(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"type": "app_usage", "data": {"normalized_content": payload["data"].upper()}}]
"""
    create_extension(ext_name, code)

    try:
        log_id = await _ingest(async_client, ext_name, {"data": "hello world"})

        # Manually run the worker task
        await task_normalize_log(None, log_id)

        # Check events
        result = await session.execute(select(Event).where(Event.source_log_id == uuid.UUID(log_id)))
        events = result.scalars().all()

        assert len(events) == 1
        event = events[0]
        assert event.source_log_id == uuid.UUID(log_id)
        assert event.event_type == "app_usage"
        assert event.data["normalized_content"] == "HELLO WORLD"

        # RawLog marked as processed
        log = await session.get(RawLog, uuid.UUID(log_id))
        assert log.processing_status == "done"

    finally:
        remove_extension(ext_name)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scenario_2_bad_code(async_client, session, mock_device_auth):
    """
    Scenario 2: The 'Bad Code' Extension (Resilience)
    """
    ext_name = "com.lifelog.crash"
    code = """
from typing import Dict, Any, List
def normalize(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raise ValueError("Boom - Intentional Crash")
"""
    create_extension(ext_name, code)

    try:
        log_id = await _ingest(async_client, ext_name, {"data": "crash me"})

        # Manually run the worker task
        await task_normalize_log(None, log_id)

        # No events should be created
        result = await session.execute(select(Event).where(Event.source_log_id == uuid.UUID(log_id)))
        events = result.scalars().all()
        assert len(events) == 0

        # RawLog marked as failed
        log = await session.get(RawLog, uuid.UUID(log_id))
        assert log.processing_status == "failed"

    finally:
        remove_extension(ext_name)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scenario_3_missing_extension(async_client, session, mock_device_auth):
    """
    Scenario 3: The 'Missing Extension'
    """
    ext_name = "com.lifelog.ghost"
    # Ensure it doesn't exist
    remove_extension(ext_name)

    log_id = await _ingest(async_client, ext_name, {"data": "ghost data"})

    # Manually run the worker task
    await task_normalize_log(None, log_id)

    # No events should be created
    result = await session.execute(select(Event).where(Event.source_log_id == uuid.UUID(log_id)))
    events = result.scalars().all()
    assert len(events) == 0

    # RawLog marked as failed
    log = await session.get(RawLog, uuid.UUID(log_id))
    assert log.processing_status == "failed"

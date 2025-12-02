import pytest
import pytest_asyncio
from httpx import AsyncClient
import os
import shutil
import uuid
from sqlalchemy import select
from app.models.data import Event
from app.models.audit import Failure

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

@pytest.mark.asyncio
@pytest.mark.integration
async def test_scenario_1_end_to_end(async_client: AsyncClient, session, mock_device_auth):
    """
    Scenario 1: The Full End-to-End Flow
    """
    # Create test extension
    ext_name = "com.lifelog.test"
    code = """
from typing import Dict, Any, List
def normalize(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"data": {"normalized_content": payload["data"].upper()}}]
"""
    create_extension(ext_name, code)
    
    try:
        payload_data = {
            "device_id": "test_device_1",
            "extension_id": ext_name,
            "payload": {
                "data": "hello world",
                "timestamp": "2023-10-27T10:00:00Z",
                "unique_id": str(uuid.uuid4())
            }
        }
        
        response = await async_client.post("/api/v1/ingest", json=payload_data)
        
        assert response.status_code == 201
        log_id = response.json()["id"]
        
        # Manually run the worker task
        await task_normalize_log(None, log_id)
        
        # Check events
        result = await session.execute(select(Event).where(Event.source_log_id == uuid.UUID(log_id)))
        events = result.scalars().all()
        
        assert len(events) == 1
        event = events[0]
        
        assert event.source_log_id == uuid.UUID(log_id)
        assert event.data["normalized_content"] == "HELLO WORLD"
        
    finally:
        remove_extension(ext_name)

@pytest.mark.asyncio
@pytest.mark.integration
async def test_scenario_2_bad_code(async_client: AsyncClient, session, mock_device_auth):
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
        payload_data = {
            "device_id": "test_device_1",
            "extension_id": ext_name,
            "payload": {
                "data": "crash me",
                "unique_id": str(uuid.uuid4())
            }
        }
        
        response = await async_client.post("/api/v1/ingest", json=payload_data)
        
        assert response.status_code == 201
        log_id = response.json()["id"]
        
        # Manually run the worker task
        await task_normalize_log(None, log_id)
        
        # Check failures
        result = await session.execute(
            select(Failure).order_by(Failure.created_at.desc()).limit(5)
        )
        failures = result.scalars().all()
        
        found = False
        for f in failures:
            if f.context and f.context.get("log_id") == log_id:
                found = True
                assert "ValueError: Boom - Intentional Crash" in f.traceback
                break
        
        assert found, "Did not find failure record for the crashing extension"
        
    finally:
        remove_extension(ext_name)

@pytest.mark.asyncio
@pytest.mark.integration
async def test_scenario_3_missing_extension(async_client: AsyncClient, session, mock_device_auth):
    """
    Scenario 3: The 'Missing Extension'
    """
    ext_name = "com.lifelog.ghost"
    # Ensure it doesn't exist
    remove_extension(ext_name)
    
    payload_data = {
        "device_id": "test_device_1",
        "extension_id": ext_name,
        "payload": {
            "data": "ghost data",
            "unique_id": str(uuid.uuid4())
        }
    }
    
    response = await async_client.post("/api/v1/ingest", json=payload_data)
    
    assert response.status_code == 201
    log_id = response.json()["id"]
    
    # Manually run the worker task
    await task_normalize_log(None, log_id)
    
    # Check failures
    result = await session.execute(
        select(Failure).order_by(Failure.created_at.desc()).limit(5)
    )
    failures = result.scalars().all()
    
    found = False
    for f in failures:
        if f.context and f.context.get("log_id") == log_id:
            found = True
            assert "FileNotFoundError" in f.traceback or "Extension processor not found" in f.traceback
            break
    
    assert found, "Did not find failure record for the missing extension"

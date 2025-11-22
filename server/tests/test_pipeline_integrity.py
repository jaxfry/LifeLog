import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import asyncio
import os
import shutil
import json
import uuid
from sqlalchemy import select
from app.main import app
from app.models.data import Event
from app.models.audit import Failure
from app.workers.main import task_normalize_log
from app.core.db import engine, get_session

# Configuration
EXTENSIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../extensions"))

@pytest_asyncio.fixture(loop_scope="function", scope="function")
async def db_session():
    # Use the same engine as the app
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.asyncio import AsyncSession
    
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with AsyncSessionLocal() as session:
        yield session

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
async def test_scenario_1_end_to_end(db_session):
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
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/ingest", json=payload_data)
        
        assert response.status_code == 201
        log_id = response.json()["id"]
        
        # Manually run the worker task
        await task_normalize_log(None, log_id)
        
        # Check events
        result = await db_session.execute(select(Event).where(Event.source_log_id == uuid.UUID(log_id)))
        events = result.scalars().all()
        
        assert len(events) == 1
        event = events[0]
        
        assert event.source_log_id == uuid.UUID(log_id)
        assert event.data["normalized_content"] == "HELLO WORLD"
        
    finally:
        remove_extension(ext_name)

@pytest.mark.asyncio
@pytest.mark.integration
async def test_scenario_2_bad_code(db_session):
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
            "device_id": "test_device_2",
            "extension_id": ext_name,
            "payload": {
                "data": "crash me",
                "unique_id": str(uuid.uuid4())
            }
        }
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/ingest", json=payload_data)
        
        assert response.status_code == 201
        log_id = response.json()["id"]
        
        # Manually run the worker task
        await task_normalize_log(None, log_id)
        
        # Check failures
        result = await db_session.execute(
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
async def test_scenario_3_missing_extension(db_session):
    """
    Scenario 3: The 'Missing Extension'
    """
    ext_name = "com.lifelog.ghost"
    # Ensure it doesn't exist
    remove_extension(ext_name)
    
    payload_data = {
        "device_id": "test_device_3",
        "extension_id": ext_name,
        "payload": {
            "data": "ghost data",
            "unique_id": str(uuid.uuid4())
        }
    }
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/ingest", json=payload_data)
    
    assert response.status_code == 201
    log_id = response.json()["id"]
    
    # Manually run the worker task
    await task_normalize_log(None, log_id)
    
    # Check failures
    result = await db_session.execute(
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

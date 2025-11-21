import pytest
import pytest_asyncio
import httpx
import asyncio
import os
import shutil
import json
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, select
from app.models.data import RawLog, Event
from app.models.audit import Failure
import time

# Configuration
API_URL = "http://localhost:8000"
DB_URL = "postgresql+asyncpg://lifelog:lifelogpassword@localhost:5432/lifelog_db"
EXTENSIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../extensions"))

# Setup DB connection
# engine = create_async_engine(DB_URL)
# AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@pytest_asyncio.fixture(loop_scope="function", scope="function")
async def db_session():
    engine = create_async_engine(DB_URL)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with AsyncSessionLocal() as session:
        yield session
    await engine.dispose()

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
async def test_scenario_1_end_to_end(db_session):
    """
    Scenario 1: The Full End-to-End Flow
    """
    print("\n--- Scenario 1: End-to-End Flow ---")
    
    # Ensure com.lifelog.test exists (it should, but let's be safe or rely on existing)
    # The existing one uppercases data.
    
    payload_data = {
        "device_id": "test_device_1",
        "extension_id": "com.lifelog.test",
        "payload": {
            "data": "hello world",
            "timestamp": "2023-10-27T10:00:00Z",
            "unique_id": str(uuid.uuid4()) # Ensure uniqueness to avoid 200 OK
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{API_URL}/api/v1/ingest", json=payload_data)
    
    assert response.status_code == 201, f"Response was {response.status_code}: {response.text}"
    log_id = response.json()["id"]
    print(f"Log Ingested: {log_id}")
    
    # Wait for worker
    print("Waiting for worker...")
    await asyncio.sleep(2)
    
    # Check events
    result = await db_session.execute(select(Event).where(Event.source_log_id == uuid.UUID(log_id)))
    events = result.scalars().all()
    
    assert len(events) == 1, f"Expected 1 event, found {len(events)}"
    event = events[0]
    
    assert event.source_log_id == uuid.UUID(log_id)
    assert event.data["normalized_content"] == "HELLO WORLD"
    print("Scenario 1 Passed!")

@pytest.mark.asyncio
async def test_scenario_2_bad_code(db_session):
    """
    Scenario 2: The 'Bad Code' Extension (Resilience)
    """
    print("\n--- Scenario 2: Bad Code Extension ---")
    
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
        
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_URL}/api/v1/ingest", json=payload_data)
        
        assert response.status_code == 201
        log_id = response.json()["id"]
        print(f"Log Ingested: {log_id}")
        
        # Wait for worker
        print("Waiting for worker...")
        await asyncio.sleep(2)
        
        # Check failures
        # We need to query the failures table. 
        # Since context is JSONB, we might need to cast or just fetch all and filter in python if needed, 
        # but filtering by context->>'log_id' is better.
        
        # Note: context is stored as JSONB.
        # In SQLAlchemy/SQLModel, we can use cast or just check.
        # Let's just fetch the failure created recently.
        
        result = await db_session.execute(
            select(Failure).order_by(Failure.created_at.desc()).limit(5)
        )
        failures = result.scalars().all()
        
        found = False
        for f in failures:
            if f.context and f.context.get("log_id") == log_id:
                found = True
                assert "ValueError: Boom - Intentional Crash" in f.traceback
                print("Found expected failure record.")
                break
        
        assert found, "Did not find failure record for the crashing extension"
        
    finally:
        remove_extension(ext_name)
    
    print("Scenario 2 Passed!")

@pytest.mark.asyncio
async def test_scenario_3_missing_extension(db_session):
    """
    Scenario 3: The 'Missing Extension'
    """
    print("\n--- Scenario 3: Missing Extension ---")
    
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
    
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{API_URL}/api/v1/ingest", json=payload_data)
    
    assert response.status_code == 201
    log_id = response.json()["id"]
    print(f"Log Ingested: {log_id}")
    
    # Wait for worker
    print("Waiting for worker...")
    await asyncio.sleep(2)
    
    # Check failures
    result = await db_session.execute(
        select(Failure).order_by(Failure.created_at.desc()).limit(5)
    )
    failures = result.scalars().all()
    
    found = False
    for f in failures:
        if f.context and f.context.get("log_id") == log_id:
            found = True
            # We expect FileNotFoundError or similar from our change in runner.py
            assert "FileNotFoundError" in f.traceback or "Extension processor not found" in f.traceback
            print("Found expected failure record for missing extension.")
            break
    
    assert found, "Did not find failure record for the missing extension"
    
    print("Scenario 3 Passed!")

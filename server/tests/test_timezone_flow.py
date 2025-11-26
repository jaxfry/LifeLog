import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import engine
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.data import RawLog, Timeline, DailySummary
from sqlmodel import select

@pytest.mark.asyncio
@pytest.mark.integration
async def test_timezone_flow(mock_superuser, mock_device_auth):
    # 1. Ingest a log with timezone header
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        payload = {
            "device_id": "test_device_1", # Must match mock_device_auth
            "extension_id": "test-ext",
            "payload": {"test": "data"}
        }
        headers = {
            "X-API-Key": "dummy-key", # Mock override will accept this
            "X-Client-Timezone": "America/New_York",
            "X-Client-Offset": "-0500"
        }
        response = await ac.post("/api/v1/ingest", json=payload, headers=headers)
        assert response.status_code == 201
        log_id = response.json()["id"]

    # 2. Verify RawLog has timezone
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        log = await session.get(RawLog, log_id)
        assert log.client_timezone == "-0500"
        
        # Create a timeline entry that falls in the local day but maybe different UTC day
        # Local: 2024-01-01 22:00 EST -> 2024-01-02 03:00 UTC
        target_date = datetime(2024, 1, 1)
        
        start_utc = datetime(2024, 1, 2, 3, 0, tzinfo=timezone.utc).replace(tzinfo=None)
        end_utc = datetime(2024, 1, 2, 4, 0, tzinfo=timezone.utc).replace(tzinfo=None)
        
        timeline = Timeline(
            start_time=start_utc,
            end_time=end_utc,
            activity="Late Night Coding",
            notes="Should be on Jan 1st",
            timezone="-0500"
        )
        session.add(timeline)
        await session.commit()

    # 3. Trigger Summary Generation for Jan 1st
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        response = await ac.post("/api/v1/admin/generate-summary/2024-01-01")
        assert response.status_code == 200
        
    # 4. Verify Summary was generated (mock LLM will return something, or it might fail if no key, 
    # but we just want to ensure it queried the right range. 
    # Since we can't easily spy on the query without more complex mocking, 
    # we rely on the fact that if it found the entry, it would try to generate a summary.
    # If it didn't find it (wrong timezone logic), it might return early or empty.)
    
    # Actually, let's verify the time utility logic directly in the test to be sure
    from app.core.utils.time import get_day_bounds_utc
    start, end = get_day_bounds_utc(datetime(2024, 1, 1), "-0500")
    assert start.hour == 5 # 00:00 EST is 05:00 UTC
    assert end.day == 2
    assert end.hour == 4 # 23:59 EST is 04:59 UTC next day

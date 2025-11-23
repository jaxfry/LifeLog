import pytest
from httpx import AsyncClient
from app.main import app
from app.models.data import Session, Event
from datetime import datetime, timedelta

@pytest.mark.asyncio
async def test_analytics_stats(async_client: AsyncClient, session):
    # Create some dummy data
    # 2 sessions, 3 events
    s1 = Session(start_time=datetime.now(), end_time=datetime.now() + timedelta(hours=1), status="PROCESSED")
    s2 = Session(start_time=datetime.now() - timedelta(days=1), end_time=datetime.now() - timedelta(days=1, hours=1), status="PENDING")
    session.add(s1)
    session.add(s2)
    
    e1 = Event(type="test", data={}, source_log_id=None) # source_log_id is required but for this test we might need to mock or create a log first.
    # Actually Event requires source_log_id which is a foreign key. 
    # Let's just test sessions for now or create a raw log.
    
    from app.models.data import RawLog
    log = RawLog(device_id="test", extension_id="test", payload={}, payload_hash="hash1")
    session.add(log)
    await session.commit()
    await session.refresh(log)
    
    e1 = Event(type="test", data={}, source_log_id=log.id)
    session.add(e1)
    await session.commit()
    
    response = await async_client.get("/api/v1/analytics/stats")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total_sessions"] == 2
    assert data["total_events"] == 1
    assert data["avg_sessions_per_day"] > 0

@pytest.mark.asyncio
async def test_activity_volume(async_client: AsyncClient, session):
    # Data already exists from previous test if session is shared, but usually it's rolled back.
    # Let's create fresh data
    s1 = Session(start_time=datetime.now(), end_time=datetime.now() + timedelta(hours=1))
    session.add(s1)
    await session.commit()
    
    response = await async_client.get("/api/v1/analytics/activity-volume?days=7")
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) > 0
    # Check if today has count >= 1
    today_str = datetime.now().strftime('%Y-%m-%d')
    found = False
    for day in data:
        if day["date"] == today_str:
            assert day["count"] >= 1
            found = True
            break
    assert found

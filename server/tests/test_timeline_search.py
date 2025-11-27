import pytest
from datetime import datetime, timedelta, timezone
from app.models.data import Timeline, DailyChapter
from uuid import uuid4

@pytest.mark.asyncio
async def test_timeline_search(async_client, session):
    # Create some timeline entries
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    t1 = Timeline(
        id=uuid4(),
        start_time=now,
        end_time=now + timedelta(hours=1),
        activity="Gym workout",
        notes="Leg day",
        category="Health"
    )
    t2 = Timeline(
        id=uuid4(),
        start_time=now - timedelta(hours=2),
        end_time=now - timedelta(hours=1),
        activity="Coding",
        notes="Working on LifeLog",
        category="Work"
    )
    t3 = Timeline(
        id=uuid4(),
        start_time=now - timedelta(hours=4),
        end_time=now - timedelta(hours=3),
        activity="Reading",
        notes="Sci-fi book",
        category="Leisure"
    )
    
    session.add(t1)
    session.add(t2)
    session.add(t3)
    await session.commit()
    
    # Search for "Gym"
    response = await async_client.get("/api/v1/timeline", params={"q": "Gym"})
    assert response.status_code == 200
    data = response.json()
    # Note: The database might contain other data from other tests or previous runs if not cleaned up.
    # So we check if at least our item is found.
    found = any(item["id"] == str(t1.id) for item in data)
    assert found
    
    # Search for "LifeLog" (in notes)
    response = await async_client.get("/api/v1/timeline", params={"q": "LifeLog"})
    assert response.status_code == 200
    data = response.json()
    found = any(item["id"] == str(t2.id) for item in data)
    assert found
    
    # Search for "Leisure" (in category)
    response = await async_client.get("/api/v1/timeline", params={"q": "Leisure"})
    assert response.status_code == 200
    data = response.json()
    found = any(item["id"] == str(t3.id) for item in data)
    assert found
    
    # Search for something that doesn't exist
    # This is tricky if the DB is not empty. We assume "NonexistentXYZ" is unique enough.
    response = await async_client.get("/api/v1/timeline", params={"q": "NonexistentXYZ"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0

@pytest.mark.asyncio
async def test_chapters_search(async_client, session):
    # Create some chapters
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    c1 = DailyChapter(
        id=uuid4(),
        date=now,
        start_time=now,
        end_time=now + timedelta(hours=1),
        title="Productive Morning",
        summary="Got a lot of coding done.",
        category="Work"
    )
    c2 = DailyChapter(
        id=uuid4(),
        date=now,
        start_time=now - timedelta(hours=2),
        end_time=now - timedelta(hours=1),
        title="Relaxing Evening",
        summary="Watched a movie.",
        category="Leisure"
    )
    
    session.add(c1)
    session.add(c2)
    await session.commit()
    
    # Search for "Productive"
    response = await async_client.get("/api/v1/chapters", params={"q": "Productive"})
    assert response.status_code == 200
    data = response.json()
    found = any(item["id"] == str(c1.id) for item in data)
    assert found
    
    # Search for "movie" (in summary)
    response = await async_client.get("/api/v1/chapters", params={"q": "movie"})
    assert response.status_code == 200
    data = response.json()
    found = any(item["id"] == str(c2.id) for item in data)
    assert found

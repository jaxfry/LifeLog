from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models.processing import TimelineEntry


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_timeline_search(async_client, session, mock_user):
    # Create some timeline entries
    n = _now()

    t1 = TimelineEntry(
        id=uuid4(),
        owner_user_id=mock_user.id,
        start_time=n,
        end_time=n + timedelta(hours=1),
        activity="Gym workout",
        notes="Leg day",
        category="Health",
    )
    t2 = TimelineEntry(
        id=uuid4(),
        owner_user_id=mock_user.id,
        start_time=n - timedelta(hours=2),
        end_time=n - timedelta(hours=1),
        activity="Coding",
        notes="Working on LifeLog",
        category="Work",
    )
    t3 = TimelineEntry(
        id=uuid4(),
        owner_user_id=mock_user.id,
        start_time=n - timedelta(hours=4),
        end_time=n - timedelta(hours=3),
        activity="Reading",
        notes="Sci-fi book",
        category="Leisure",
    )

    session.add(t1)
    session.add(t2)
    session.add(t3)
    await session.commit()

    # Search for "Gym"
    response = await async_client.get("/api/v1/timeline", params={"q": "Gym"})
    assert response.status_code == 200
    data = response.json()
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
    response = await async_client.get("/api/v1/timeline", params={"q": "NonexistentXYZ"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0

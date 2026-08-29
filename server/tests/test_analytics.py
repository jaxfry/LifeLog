from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from app.models.ingest import Event, RawLog
from app.models.processing import Session


@pytest.mark.asyncio
async def test_analytics_stats(async_client: AsyncClient, session, mock_user):
    # Create some dummy data: 2 sessions, 1 event
    s1 = Session(
        owner_user_id=mock_user.id,
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=1),
        status="processed",
    )
    s2 = Session(
        start_time=datetime.now() - timedelta(days=1),
        end_time=datetime.now() - timedelta(hours=23),
        status="pending",
        owner_user_id=mock_user.id,
    )
    session.add(s1)
    session.add(s2)

    # Create a raw log first (needed for foreign key)
    log = RawLog(
        owner_user_id=mock_user.id,
        device_id="test",
        extension_id="test",
        payload={},
        payload_hash="hash_analytics_1",
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)

    e1 = Event(owner_user_id=mock_user.id, event_type="test", data={}, source_log_id=log.id, start_time=datetime.now())
    session.add(e1)
    await session.commit()

    response = await async_client.get("/api/v1/analytics/stats")
    assert response.status_code == 200
    data = response.json()

    assert data["total_sessions"] >= 2
    assert data["total_events"] >= 1
    assert "avg_sessions_per_day" in data


@pytest.mark.asyncio
async def test_activity_volume(async_client: AsyncClient, session, mock_user):
    s1 = Session(owner_user_id=mock_user.id, start_time=datetime.now(), end_time=datetime.now() + timedelta(hours=1))
    session.add(s1)
    await session.commit()

    response = await async_client.get("/api/v1/analytics/activity-volume?days=7")
    assert response.status_code == 200
    data = response.json()

    assert len(data) > 0
    today_str = datetime.now().strftime("%Y-%m-%d")
    found = False
    for day in data:
        if day["date"] == today_str:
            assert day["count"] >= 1
            found = True
            break
    assert found


@pytest.mark.asyncio
async def test_status_distribution(async_client: AsyncClient, session, mock_user):
    s1 = Session(
        owner_user_id=mock_user.id,
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=1),
        status="completed",
    )
    session.add(s1)
    await session.commit()

    response = await async_client.get("/api/v1/analytics/status-distribution")
    assert response.status_code == 200
    data = response.json()

    statuses = {row["name"]: row["value"] for row in data}
    assert statuses.get("completed", 0) >= 1


@pytest.mark.asyncio
async def test_dashboard_metrics(async_client: AsyncClient, session, mock_user):
    log = RawLog(
        owner_user_id=mock_user.id,
        device_id="test",
        extension_id="test",
        payload={},
        payload_hash="hash_dash_1",
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)

    event = Event(
        owner_user_id=mock_user.id,
        event_type="app_usage",
        data={},
        source_log_id=log.id,
        start_time=datetime.now(),
    )
    session.add(event)

    s1 = Session(owner_user_id=mock_user.id, start_time=datetime.now(), end_time=datetime.now() + timedelta(hours=1))
    session.add(s1)
    await session.commit()

    response = await async_client.get("/api/v1/analytics/dashboard-metrics")
    assert response.status_code == 200
    data = response.json()

    assert data["total_events"] >= 1
    assert "active_collectors" in data
    assert "ai_processing" in data
    assert len(data["activity_volume"]) >= 7

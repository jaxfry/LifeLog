from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.integration
async def test_commitment_lifecycle_and_notification(mock_user, async_client: AsyncClient):
    due = datetime.now(UTC) + timedelta(days=1)
    response = await async_client.post(
        "/api/v1/commitments",
        json={"title": "Review the report", "due_at": due.isoformat()},
    )
    assert response.status_code == 201
    commitment = response.json()
    assert commitment["status"] == "planned"

    response = await async_client.post(
        f"/api/v1/commitments/{commitment['id']}/progress",
        json={"amount": 30, "unit": "minutes", "note": "Reviewed the introduction"},
    )
    assert response.status_code == 201
    assert response.json()["amount"] == 30

    response = await async_client.get(f"/api/v1/commitments/{commitment['id']}/progress")
    assert len(response.json()) == 1

    response = await async_client.get("/api/v1/notifications")
    assert response.status_code == 200
    assert response.json()[0]["commitment_id"] == commitment["id"]

    response = await async_client.patch(
        f"/api/v1/commitments/{commitment['id']}",
        json={"status": "completed"},
    )
    assert response.status_code == 200
    assert response.json()["completed_at"] is not None

    response = await async_client.get("/api/v1/notifications")
    assert response.json() == []


@pytest.mark.asyncio
async def test_commitments_require_authentication(async_client: AsyncClient):
    response = await async_client.get("/api/v1/commitments")
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.integration
async def test_planner_uses_estimate_and_recorded_progress(mock_user, async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/commitments",
        json={
            "title": "Prepare presentation",
            "due_at": "2026-09-03T17:00:00Z",
            "data": {"estimated_minutes": 90},
        },
    )
    commitment = response.json()
    await async_client.post(
        f"/api/v1/commitments/{commitment['id']}/progress",
        json={"amount": 30, "unit": "minutes"},
    )

    response = await async_client.post(
        "/api/v1/plan/generate",
        json={
            "start_at": "2026-09-01T09:00:00Z",
            "end_at": "2026-09-02T18:00:00Z",
            "daily_capacity_minutes": 60,
            "block_minutes": 30,
        },
    )
    assert response.status_code == 200
    blocks = response.json()
    assert len(blocks) == 2
    assert all(block["commitment_id"] == commitment["id"] for block in blocks)

    response = await async_client.patch(f"/api/v1/plan/{blocks[0]['id']}", json={"status": "accepted"})
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"

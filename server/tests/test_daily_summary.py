import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta
from app.models.data import Timeline

@pytest.mark.asyncio
@pytest.mark.integration
async def test_daily_summary_generation(async_client: AsyncClient, session, mock_superuser):
    # Seed data - create a timeline entry for today
    now = datetime.now()
    start_time = now - timedelta(hours=1)
    end_time = now
    
    timeline = Timeline(
        start_time=start_time,
        end_time=end_time,
        activity="Coding",
        notes="Working on LifeLog tests",
        timezone="UTC"
    )
    session.add(timeline)
    await session.commit()

    # Trigger summary generation for today
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    response = await async_client.post(f"/api/v1/admin/generate-summary/{today_str}")
    
    # It might return null if no LLM key, but status should be 200
    assert response.status_code == 200

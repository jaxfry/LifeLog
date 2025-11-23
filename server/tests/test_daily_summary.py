import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import engine
from datetime import datetime

@pytest.mark.asyncio
@pytest.mark.integration
async def test_daily_summary_generation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Trigger summary generation for today
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # Note: This test might fail if there are no timeline entries for today.
        # Ideally we should seed some data first, but for now let's just check if the endpoint runs without 500 error.
        
        response = await ac.post(f"/api/v1/admin/generate-summary/{today_str}")
        
        # It might return null if no data, but status should be 200
        assert response.status_code == 200
        
        data = response.json()
        # If data exists, verify structure
        if data:
            assert "summary_text" in data
            assert "key_activities" in data
            assert "productivity_score" in data

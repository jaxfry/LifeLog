import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import engine
from datetime import datetime, timedelta
from app.models.data import Timeline
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.asyncio
@pytest.mark.integration
async def test_daily_summary_generation(mock_superuser):
    # Seed data
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        # Create a timeline entry for today
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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        # Trigger summary generation for today
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        response = await ac.post(f"/api/v1/admin/generate-summary/{today_str}")
        
        # It might return null if no data, but status should be 200
        assert response.status_code == 200
        
        data = response.json()
        # If data exists, verify structure
        if data:
            assert "summary_text" in data
            assert "key_activities" in data
            assert "productivity_score" in data

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import select

from app.models.processing import DailySummary, TimelineEntry
from app.models.retrieval import SearchDocument


@pytest.mark.asyncio
@pytest.mark.integration
async def test_daily_summary_generation(async_client: AsyncClient, session, mock_superuser):
    # Seed data - create a timeline entry for today
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    timeline = TimelineEntry(
        start_time=now - timedelta(hours=1),
        end_time=now,
        activity="Coding",
        notes="Working on LifeLog tests",
        logical_date=today_str,
        is_summarized=True,
    )
    session.add(timeline)
    await session.commit()

    # Trigger summary generation for today
    response = await async_client.post(f"/api/v1/admin/process/summarize/{today_str}")

    # No LLM key configured -> summary marked failed, but the route returns 200
    assert response.status_code == 200
    data = response.json()
    assert data["logical_date"] == today_str

    summary = await session.get(DailySummary, today_str)
    assert summary is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_daily_summary_generation_empty_day(async_client: AsyncClient, session, mock_superuser):
    today_str = datetime.now().strftime("%Y-%m-%d")

    response = await async_client.post(f"/api/v1/admin/process/summarize/{today_str}")

    assert response.status_code == 200
    data = response.json()
    assert data["logical_date"] == today_str
    assert "No activities recorded" in data["summary_text"]
    document = (
        await session.execute(
            select(SearchDocument).where(
                SearchDocument.source_type == "daily_summary",
                SearchDocument.logical_date == today_str,
            )
        )
    ).scalars().one()
    assert document.content == data["summary_text"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_daily_summary_invalid_date(async_client: AsyncClient, session, mock_superuser):
    response = await async_client.post("/api/v1/admin/process/summarize/not-a-date")

    assert response.status_code == 400

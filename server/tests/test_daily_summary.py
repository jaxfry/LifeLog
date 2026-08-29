from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlmodel import select

from app.models.captures import Capture
from app.models.processing import DailySummary, TimelineEntry
from app.models.retrieval import SearchDocument
from app.services.summarizer import generate_daily_summary


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

    summary = (
        await session.execute(
            select(DailySummary).where(DailySummary.logical_date == today_str)
        )
    ).scalar_one_or_none()
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


@pytest.mark.asyncio
@pytest.mark.integration
async def test_daily_summary_allows_reasoning_model_headroom(session):
    logical_date = "2026-08-12"
    session.add(
        TimelineEntry(
            start_time=datetime(2026, 8, 12, 9),
            end_time=datetime(2026, 8, 12, 10),
            activity="Studying",
            logical_date=logical_date,
        )
    )
    await session.commit()
    completion = AsyncMock(return_value="A focused day of studying.")

    with patch("app.services.summarizer.call_llm", completion):
        summary = await generate_daily_summary(session, logical_date)

    assert summary.summary_text == "A focused day of studying."
    assert completion.await_args.kwargs["max_tokens"] == 4096


@pytest.mark.asyncio
@pytest.mark.integration
async def test_daily_summary_fuses_captures_and_structured_open_loops(session):
    logical_date = "2026-08-12"
    session.add(
        TimelineEntry(
            start_time=datetime(2026, 8, 12, 17),
            end_time=datetime(2026, 8, 12, 18),
            activity="Physics practice",
            notes="Worked in the physics worksheet.",
            logical_date=logical_date,
        )
    )
    session.add(
        Capture(
            kind="note",
            captured_at=datetime(2026, 8, 13, 0, 26),
            timezone="America/Vancouver",
            intent="progress_note",
            text_content="still need questions 7-12",
            status="ready",
        )
    )
    await session.commit()
    completion = AsyncMock(
        return_value='{"summary":"Worked on physics, with part of the worksheet unfinished.",'
        '"key_activities":["Practised physics"],'
        '"open_loops":["Finish questions 7-12"],"productivity_score":null,'
        '"mood":null,"inferences":[]}'
    )

    with patch("app.services.summarizer.call_llm", completion):
        summary = await generate_daily_summary(session, logical_date)

    assert summary.key_activities == ["Practised physics"]
    assert summary.open_loops == ["Finish questions 7-12"]
    assert "still need questions 7-12" in completion.await_args.kwargs["user_prompt"]

from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

from app.models.processing import Session, TimelineEntry
from app.services.ingestion import ingest_log
from app.services.sessionizer import run_sessionizer
from app.services.timeline import process_pending_sessions
from app.workers.process import process_log


@pytest.mark.asyncio
async def test_full_pipeline(session):
    # 1. Ingest Log
    payload = {"timestamp": "2023-01-01T12:00:00Z", "duration": 60, "app": "VS Code"}
    raw_log, created = await ingest_log(session, "device1", "com.lifelog.test", payload)
    assert created
    assert raw_log.id is not None

    # 2. Process Log (Mock normalization)
    with patch("app.workers.process.run_normalization") as mock_norm:
        mock_norm.return_value = [{"type": "app_usage", "data": payload}]

        events = await process_log(session, raw_log.id)
        assert len(events) == 1
        assert events[0].source_log_id == raw_log.id

    # 3. Sessionize
    await run_sessionizer(session)

    # Verify session created
    stmt = select(Session).where(Session.status == "pending")
    result = await session.execute(stmt)
    sessions = result.scalars().all()
    assert len(sessions) == 1
    db_session = sessions[0]
    assert db_session.status == "pending"

    # 4. Timeline Processing (Mock LLM)

    with patch("app.services.timeline.call_llm", new_callable=AsyncMock) as mock_completion:
        mock_completion.return_value = "Coding in VS Code"
        with patch("app.services.timeline.get_prompt", return_value="Describe the session: {events}"):
            await process_pending_sessions(session)

    # Verify Timeline
    await session.refresh(db_session)
    assert db_session.status == "completed"

    stmt = select(TimelineEntry).where(TimelineEntry.session_id == db_session.id)
    result = await session.execute(stmt)
    timeline_entries = result.scalars().all()
    assert len(timeline_entries) == 1
    assert timeline_entries[0].activity == "Coding in VS Code"

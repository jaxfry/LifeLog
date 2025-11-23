import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from app.core.ingestion import ingest_log
from app.core.processing import process_log
from app.core.sessionizer import run_sessionizer
from app.core.timeline_processor import process_pending_sessions
from app.models.data import RawLog, Event, Session, Timeline, SessionStatus
from sqlmodel import select

@pytest.mark.asyncio
async def test_full_pipeline(session):
    # 1. Ingest Log
    payload = {"timestamp": "2023-01-01T12:00:00Z", "duration": 60, "app": "VS Code"}
    raw_log, created = await ingest_log(session, "device1", "com.lifelog.test", payload)
    assert created
    assert raw_log.id is not None

    # 2. Process Log (Mock normalization)
    # We mock run_normalization to avoid needing a real extension file on disk
    with patch("app.core.processing.run_normalization") as mock_norm:
        mock_norm.return_value = [{"type": "app_usage", "data": payload}]
        
        events = await process_log(session, raw_log.id)
        assert len(events) == 1
        assert events[0].source_log_id == raw_log.id

    # 3. Sessionize
    # This should group the event into a new session
    await run_sessionizer(session)
    
    # Verify session created
    stmt = select(Session).where(Session.status == SessionStatus.PENDING)
    result = await session.execute(stmt)
    sessions = result.scalars().all()
    assert len(sessions) == 1
    db_session = sessions[0]
    assert db_session.status == SessionStatus.PENDING

    # 4. Timeline Processing (Mock LLM)
    # We mock the LLM response to return a valid JSON timeline
    mock_llm_response = MagicMock()
    mock_llm_response.choices = [MagicMock(message=MagicMock(content='[{"start": "2023-01-01T12:00:00Z", "end": "2023-01-01T12:01:00Z", "activity": "Coding", "notes": "VS Code"}]'))]
    
    with patch("app.core.timeline_processor.acompletion", return_value=mock_llm_response) as mock_llm:
        # Also mock get_gemini_api_key to avoid env var check failure if not set
        with patch("app.core.timeline_processor.get_gemini_api_key", return_value="fake_key"):
             # Mock get_system_prompt to avoid DB lookup if table empty
            with patch("app.core.timeline_processor.get_system_prompt", return_value="Prompt"):
                await process_pending_sessions(session)

    # Verify Timeline
    await session.refresh(db_session)
    assert db_session.status == SessionStatus.PROCESSED
    
    stmt = select(Timeline).where(Timeline.session_id == db_session.id)
    result = await session.execute(stmt)
    timeline_entries = result.scalars().all()
    assert len(timeline_entries) == 1
    assert timeline_entries[0].activity == "Coding"

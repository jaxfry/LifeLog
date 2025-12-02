import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import uuid
from app.core.timeline_processor import process_session
from app.models.data import Session, Event, Timeline, SessionStatus
from sqlmodel import select

@pytest.mark.asyncio
async def test_process_session_success(session):
    # Setup Data
    start_time = datetime(2023, 1, 1, 12, 0, 0)
    end_time = datetime(2023, 1, 1, 13, 0, 0)
    
    # Create RawLog first (required by Event FK)
    from app.models.data import RawLog
    raw_log = RawLog(
        device_id="dev1",
        extension_id="ext1",
        payload={"data": "test"},
        payload_hash=f"hash_{uuid.uuid4()}"
    )
    session.add(raw_log)
    await session.commit()
    await session.refresh(raw_log)

    db_session = Session(
        start_time=start_time,
        end_time=end_time,
        status=SessionStatus.PENDING
    )
    session.add(db_session)
    await session.commit()
    await session.refresh(db_session)
    
    event = Event(
        source_log_id=raw_log.id,
        session_id=db_session.id,
        type="test",
        data={"msg": "hello"},
        created_at=start_time,
        is_superseded=False
    )
    session.add(event)
    await session.commit()

    # Mock LLM
    mock_content = '[{"start": "2023-01-01T12:00:00Z", "end": "2023-01-01T13:00:00Z", "activity": "Test Activity", "notes": "Notes"}]'
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=mock_content))]

    with patch("app.core.timeline_processor.acompletion", return_value=mock_response):
        with patch("app.core.timeline_processor.get_gemini_api_key", return_value="fake_key"):
            with patch("app.core.timeline_processor.get_system_prompt", return_value="Prompt"):
                await process_session(session, db_session)

    # Verify
    await session.refresh(db_session)
    assert db_session.status == SessionStatus.PROCESSED
    
    stmt = select(Timeline).where(Timeline.session_id == db_session.id)
    result = await session.execute(stmt)
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].activity == "Test Activity"

@pytest.mark.asyncio
async def test_process_session_failure_retry(session):
    # Setup Data
    db_session = Session(
        start_time=datetime.now(),
        end_time=datetime.now(),
        status=SessionStatus.PENDING,
        retry_count=0
    )
    session.add(db_session)
    await session.commit()
    await session.refresh(db_session)

    # Create RawLog and Event so session is not skipped
    from app.models.data import RawLog
    raw_log = RawLog(
        device_id="dev1",
        extension_id="ext1",
        payload={"data": "test"},
        payload_hash=f"hash_{uuid.uuid4()}"
    )
    session.add(raw_log)
    await session.commit()
    await session.refresh(raw_log)

    event = Event(
        source_log_id=raw_log.id,
        session_id=db_session.id,
        type="test",
        data={"msg": "hello"},
        created_at=datetime.now(),
        is_superseded=False
    )
    session.add(event)
    await session.commit()

    # Mock LLM Failure
    with patch("app.core.timeline_processor.acompletion", side_effect=Exception("LLM Error")):
        with patch("app.core.timeline_processor.get_gemini_api_key", return_value="fake_key"):
             with patch("app.core.timeline_processor.get_system_prompt", return_value="Prompt"):
                await process_session(session, db_session)

    # Verify Retry Count
    await session.refresh(db_session)
    assert db_session.retry_count == 1
    assert db_session.status == SessionStatus.PENDING

from datetime import datetime
from unittest.mock import patch

import pytest
from sqlmodel import select

from app.models.ingest import Event, RawLog
from app.models.processing import Session, TimelineEntry
from app.services.timeline import generate_timeline_for_session


async def _create_session_with_event(session, status="pending", retry_count=0):
    raw_log = RawLog(
        device_id="dev1",
        extension_id="ext1",
        payload={"data": "test"},
        payload_hash="hash_timeline_1",
    )
    session.add(raw_log)
    await session.commit()
    await session.refresh(raw_log)

    start_time = datetime(2023, 1, 1, 12, 0, 0)
    db_session = Session(
        start_time=start_time,
        end_time=datetime(2023, 1, 1, 13, 0, 0),
        status=status,
        retry_count=retry_count,
    )
    session.add(db_session)
    await session.commit()
    await session.refresh(db_session)

    event = Event(
        source_log_id=raw_log.id,
        session_id=db_session.id,
        event_type="app_usage",
        start_time=start_time,
        data={"app": "VS Code"},
        is_superseded=False,
    )
    session.add(event)
    await session.commit()

    return db_session


@pytest.mark.asyncio
async def test_generate_timeline_success(session):
    db_session = await _create_session_with_event(session)

    with patch("app.services.timeline.call_llm", return_value="Coding in VS Code"):
        entry = await generate_timeline_for_session(session, db_session)

    assert entry is not None
    assert entry.activity == "Coding in VS Code"
    assert entry.session_id == db_session.id

    await session.refresh(db_session)
    assert db_session.status == "completed"
    assert db_session.processing_status == "completed"

    stmt = select(TimelineEntry).where(TimelineEntry.session_id == db_session.id)
    result = await session.execute(stmt)
    entries = result.scalars().all()
    assert len(entries) == 1


@pytest.mark.asyncio
async def test_generate_timeline_failure_retry(session):
    db_session = await _create_session_with_event(session, retry_count=0)

    with patch("app.services.timeline.call_llm", side_effect=RuntimeError("LLM Error")):
        entry = await generate_timeline_for_session(session, db_session)

    assert entry is None

    await session.refresh(db_session)
    assert db_session.status == "failed"
    assert db_session.processing_status == "failed"
    assert db_session.retry_count == 1


@pytest.mark.asyncio
async def test_generate_timeline_skips_non_pending(session):
    db_session = await _create_session_with_event(session, status="completed")

    entry = await generate_timeline_for_session(session, db_session)

    assert entry is None


@pytest.mark.asyncio
async def test_generate_timeline_no_events_completes_session(session):
    db_session = Session(
        start_time=datetime(2023, 1, 1, 12, 0, 0),
        end_time=datetime(2023, 1, 1, 13, 0, 0),
        status="pending",
    )
    session.add(db_session)
    await session.commit()

    entry = await generate_timeline_for_session(session, db_session)

    assert entry is None
    await session.refresh(db_session)
    assert db_session.status == "completed"

    # No events linked -> no Event rows exist at all in this test
    result = await session.execute(select(Event))
    assert len(result.scalars().all()) == 0

import uuid
from datetime import datetime

import pytest

from app.models.ingest import Event, RawLog
from app.models.processing import Session
from app.services.processing import (
    get_sessions_ready_for_ai,
    run_processing_pipeline,
)


def _make_raw_log(session, device_id: str = "dev") -> RawLog:
    rl = RawLog(
        device_id=device_id,
        extension_id="test.ext",
        payload={"test": True},
        payload_hash=f"hash_{uuid.uuid4().hex}",
    )
    session.add(rl)
    return rl


@pytest.mark.asyncio
async def test_run_processing_pipeline_creates_sessions(session):
    rl = _make_raw_log(session)
    await session.flush()
    e1 = Event(
        source_log_id=rl.id,
        event_type="app_usage",
        start_time=datetime(2024, 6, 1, 10, 0, 0),
        end_time=datetime(2024, 6, 1, 10, 30, 0),
    )
    e2 = Event(
        source_log_id=rl.id,
        event_type="app_usage",
        start_time=datetime(2024, 6, 1, 10, 35, 0),
        end_time=datetime(2024, 6, 1, 11, 0, 0),
    )
    session.add(e1)
    session.add(e2)
    await session.commit()

    result = await run_processing_pipeline(session)
    assert result["sessions_created"] == 1
    assert result["sessions_marked_dirty"] == 0


@pytest.mark.asyncio
async def test_get_sessions_ready_for_ai(session, mock_user):
    s1 = Session(
        start_time=datetime(2024, 6, 1, 10, 0, 0),
        end_time=datetime(2024, 6, 1, 11, 0, 0),
        status="pending",
        processing_status="ready",
        owner_user_id=mock_user.id,
    )
    s2 = Session(
        start_time=datetime(2024, 6, 1, 14, 0, 0),
        end_time=datetime(2024, 6, 1, 15, 0, 0),
        status="pending",
        processing_status="ready",
        owner_user_id=mock_user.id,
    )
    s3 = Session(
        start_time=datetime(2024, 6, 1, 20, 0, 0),
        end_time=datetime(2024, 6, 1, 21, 0, 0),
        status="completed",
        processing_status="completed",
        owner_user_id=mock_user.id,
    )
    session.add(s1)
    session.add(s2)
    session.add(s3)
    await session.commit()

    ready = await get_sessions_ready_for_ai(session, limit=10)
    assert len(ready) == 2
    assert ready[0].id == s1.id
    assert ready[1].id == s2.id


@pytest.mark.asyncio
async def test_get_sessions_ready_for_ai_respects_limit(session, mock_user):
    sessions = [
        Session(
            start_time=datetime(2024, 6, 1, 10 + i, 0, 0),
            end_time=datetime(2024, 6, 1, 11 + i, 0, 0),
            status="pending",
            processing_status="ready",
            owner_user_id=mock_user.id,
        )
        for i in range(5)
    ]
    for s in sessions:
        session.add(s)
    await session.commit()

    ready = await get_sessions_ready_for_ai(session, limit=3)
    assert len(ready) == 3

import uuid
from datetime import datetime

import pytest
from sqlmodel import select

from app.models.ingest import Event, RawLog
from app.models.processing import Session
from app.services.sessionizer import (
    _group_into_sessions,
    run_sessionizer,
)


@pytest.mark.asyncio
async def test_group_into_sessions_single_event():
    events = [
        Event(
            event_type="app_usage",
            start_time=datetime(2024, 1, 1, 10, 0, 0),
            end_time=datetime(2024, 1, 1, 10, 30, 0),
        ),
    ]
    groups = _group_into_sessions(events)
    assert len(groups) == 1
    assert len(groups[0]) == 1


@pytest.mark.asyncio
async def test_group_into_sessions_merges_close_events():
    events = [
        Event(
            event_type="app_usage",
            start_time=datetime(2024, 1, 1, 10, 0, 0),
            end_time=datetime(2024, 1, 1, 10, 15, 0),
        ),
        Event(
            event_type="app_usage",
            start_time=datetime(2024, 1, 1, 10, 20, 0),
            end_time=datetime(2024, 1, 1, 10, 35, 0),
        ),
    ]
    groups = _group_into_sessions(events)
    assert len(groups) == 1
    assert len(groups[0]) == 2


@pytest.mark.asyncio
async def test_group_into_sessions_splits_distant_events():
    events = [
        Event(
            event_type="app_usage",
            start_time=datetime(2024, 1, 1, 10, 0, 0),
            end_time=datetime(2024, 1, 1, 10, 15, 0),
        ),
        Event(
            event_type="app_usage",
            start_time=datetime(2024, 1, 1, 11, 0, 0),
            end_time=datetime(2024, 1, 1, 11, 15, 0),
        ),
    ]
    groups = _group_into_sessions(events)
    assert len(groups) == 2


@pytest.mark.asyncio
async def test_group_into_sessions_splits_across_dates():
    events = [
        Event(
            event_type="app_usage",
            start_time=datetime(2024, 1, 1, 23, 50, 0),
            end_time=datetime(2024, 1, 1, 23, 55, 0),
        ),
        Event(
            event_type="app_usage",
            start_time=datetime(2024, 1, 2, 0, 5, 0),
            end_time=datetime(2024, 1, 2, 0, 10, 0),
        ),
    ]
    groups = _group_into_sessions(events)
    assert len(groups) == 2


def _make_raw_log(session, extension_id: str = "test.ext") -> RawLog:
    rl = RawLog(
        device_id="test_dev",
        extension_id=extension_id,
        payload={"test": True},
        payload_hash=f"hash_{uuid.uuid4().hex}",
    )
    session.add(rl)
    return rl


@pytest.mark.asyncio
async def test_run_sessionizer_creates_sessions(session):
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

    count = await run_sessionizer(session)
    assert count == 1

    result = await session.execute(select(Session))
    sessions = result.scalars().all()
    assert len(sessions) == 1
    assert sessions[0].status == "pending"

    result = await session.execute(select(Event))
    events = result.scalars().all()
    for e in events:
        assert e.session_id == sessions[0].id


@pytest.mark.asyncio
async def test_run_sessionizer_skips_sessioned_events(session):
    rl = _make_raw_log(session)

    ses = Session(
        start_time=datetime(2024, 6, 1, 10, 0, 0),
        end_time=datetime(2024, 6, 1, 11, 0, 0),
        status="pending",
    )
    session.add(ses)
    await session.flush()

    e1 = Event(
        source_log_id=rl.id,
        event_type="app_usage",
        start_time=datetime(2024, 6, 1, 10, 0, 0),
        end_time=datetime(2024, 6, 1, 10, 30, 0),
        session_id=ses.id,
    )
    e2 = Event(
        source_log_id=rl.id,
        event_type="app_usage",
        start_time=datetime(2024, 6, 1, 10, 0, 0),
        end_time=datetime(2024, 6, 1, 10, 30, 0),
    )
    session.add(e1)
    session.add(e2)
    await session.commit()

    count = await run_sessionizer(session)
    assert count == 1

    result = await session.execute(select(Session))
    sessions = result.scalars().all()
    assert len(sessions) == 2

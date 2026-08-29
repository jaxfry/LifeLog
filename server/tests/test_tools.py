import uuid
from datetime import datetime, timedelta

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from sqlmodel import select

from app.models.config import Extension
from app.models.context import ReviewItem
from app.models.files import Commitment, CommitmentProgress, PlanBlock
from app.models.ingest import Event, RawLog
from app.models.sources import SourceConnection, SourceRecord
from app.services.kernel import create_entity, link_event
from app.services.measurements import create_measurement
from app.services.tools import execute_tool, tool_catalog

T0 = datetime(2024, 1, 1, 9, 0, 0)


def _dt(hour: int) -> datetime:
    return datetime(2024, 1, 1, hour, 0, 0)


async def _persist_user(session, user) -> None:
    session.add(user)
    await session.commit()


async def _event(session, event_type: str, data: dict, start: datetime) -> Event:
    raw = RawLog(
        device_id="test_dev",
        extension_id="com.lifelog.aw",
        payload={"test": True},
        payload_hash=f"hash_{uuid.uuid4().hex}",
    )
    session.add(raw)
    await session.flush()
    event = Event(
        source_log_id=raw.id,
        event_type=event_type,
        start_time=start,
        data=data,
        logical_date=start.strftime("%Y-%m-%d"),
    )
    session.add(event)
    await session.flush()
    return event


@pytest.mark.asyncio
@pytest.mark.integration
async def test_catalog_lists_all_tools(session):
    catalog = tool_catalog()
    assert '"calculate_duration"' in catalog
    assert '"propose_action"' in catalog
    assert '"aggregate_measurements"' in catalog


@pytest.mark.asyncio
@pytest.mark.integration
async def test_calculate_duration_tool(session, mock_user):
    await _persist_user(session, mock_user)
    course = await create_entity(session, entity_type="course", name="Calculus", owner_user_id=mock_user.id)
    first = await _event(session, "study_session", {"course_name": "Calculus", "duration": 3600}, _dt(9))
    second = await _event(session, "study_session", {"course_name": "Calculus", "duration": 1800}, _dt(14))
    await session.commit()
    for event in (first, second):
        await link_event(
            session,
            event_id=event.id,
            predicate="studied_for",
            object_id=course.id,
            object_type="entity",
            occurred_from=event.start_time,
            occurred_until=event.start_time + timedelta(seconds=float(event.data["duration"])),
            source_event_id=event.id,
            extractor="test",
            extraction_version=1,
        )
    await session.commit()

    result = await execute_tool(
        session,
        user_id=mock_user.id,
        area_id=None,
        name="calculate_duration",
        arguments={"predicate": "studied_for", "entity_name": "Calculus", "entity_type": "course"},
    )
    assert result["total_seconds"] == 5400.0
    assert result["per_entity"][0]["name"] == "Calculus"
    assert result["per_entity"][0]["hours"] == 1.5


@pytest.mark.asyncio
@pytest.mark.integration
async def test_calculate_duration_unknown_entity(session, mock_user):
    result = await execute_tool(
        session,
        user_id=mock_user.id,
        area_id=None,
        name="calculate_duration",
        arguments={"entity_name": "Nope"},
    )
    assert result["error"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_aggregate_measurements_tool(session, mock_user):
    await _persist_user(session, mock_user)
    course = await create_entity(session, entity_type="course", name="CS 101", owner_user_id=mock_user.id)
    for score in (80.0, 90.0):
        await create_measurement(
            session,
            entity_id=course.id,
            metric="exam_score",
            value=score,
            unit="percent",
            occurred_at=T0,
        )
    await session.commit()

    result = await execute_tool(
        session,
        user_id=mock_user.id,
        area_id=None,
        name="aggregate_measurements",
        arguments={"entity_name": "CS 101", "metric": "exam_score"},
    )
    assert result["measurements"][0]["average"] == 85.0
    assert result["measurements"][0]["count"] == 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_deadlines_and_inspect_progress(session, mock_user):
    await _persist_user(session, mock_user)
    commitment = Commitment(
        owner_user_id=mock_user.id,
        title="Essay draft",
        status="planned",
        due_at=_dt(18),
        description="Write the draft",
        data={},
    )
    session.add(commitment)
    await session.flush()
    session.add(
        CommitmentProgress(
            owner_user_id=mock_user.id,
            commitment_id=commitment.id,
            amount=30.0,
            unit="minutes",
            observed_at=_dt(10),
            note="outline",
        )
    )
    await session.commit()

    deadlines = await execute_tool(
        session, user_id=mock_user.id, area_id=None, name="list_deadlines", arguments={}
    )
    assert deadlines["deadlines"][0]["title"] == "Essay draft"

    progress = await execute_tool(
        session,
        user_id=mock_user.id,
        area_id=None,
        name="inspect_commitment_progress",
        arguments={"commitment_title": "Essay"},
    )
    assert progress["commitment"]["status"] == "planned"
    assert progress["progress"][0]["amount"] == 30.0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_find_conflicts_and_generate_plan(session, mock_user):
    await _persist_user(session, mock_user)
    commitment = Commitment(
        owner_user_id=mock_user.id,
        title="Assignment",
        status="planned",
        due_at=_dt(20),
        data={},
    )
    session.add(commitment)
    await session.flush()
    session.add(
        PlanBlock(
            owner_user_id=mock_user.id,
            commitment_id=commitment.id,
            start_at=_dt(10),
            end_at=_dt(12),
            status="accepted",
            rationale="fixed",
        )
    )
    session.add(
        PlanBlock(
            owner_user_id=mock_user.id,
            commitment_id=commitment.id,
            start_at=_dt(11),
            end_at=_dt(13),
            status="accepted",
            rationale="fixed 2",
        )
    )
    await session.commit()

    conflicts = await execute_tool(
        session,
        user_id=mock_user.id,
        area_id=None,
        name="find_scheduling_conflicts",
        arguments={"occurred_from": _dt(9).isoformat(), "occurred_until": _dt(14).isoformat()},
    )
    assert conflicts["conflicts"][0]["overlap_minutes"] == 60

    plan = await execute_tool(
        session,
        user_id=mock_user.id,
        area_id=None,
        name="generate_plan",
        arguments={"horizon_days": 1, "daily_capacity_minutes": 120, "block_minutes": 45},
    )
    assert "blocks" in plan


@pytest.mark.asyncio
@pytest.mark.integration
async def test_compare_time_periods_tool(session, mock_user):
    await _persist_user(session, mock_user)
    course = await create_entity(session, entity_type="course", name="Physics", owner_user_id=mock_user.id)
    for start, duration in ((_dt(9), 3600), (_dt(14), 1800)):
        event = await _event(
            session, "study_session", {"course_name": "Physics", "duration": duration}, start
        )
        await link_event(
            session,
            event_id=event.id,
            predicate="studied_for",
            object_id=course.id,
            object_type="entity",
            occurred_from=event.start_time,
            occurred_until=event.start_time + timedelta(seconds=duration),
            source_event_id=event.id,
            extractor="test",
            extraction_version=1,
        )
    await session.commit()

    result = await execute_tool(
        session,
        user_id=mock_user.id,
        area_id=None,
        name="compare_time_periods",
        arguments={
            "entity_name": "Physics",
            "predicate": "studied_for",
            "from_1": _dt(8).isoformat(),
            "until_1": _dt(12).isoformat(),
            "from_2": _dt(12).isoformat(),
            "until_2": _dt(18).isoformat(),
        },
    )
    assert result["period_1_seconds"] == 3600.0
    assert result["period_2_seconds"] == 1800.0
    assert result["delta_seconds"] == -1800.0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_resolve_source_history_tool(session, mock_user):
    await _persist_user(session, mock_user)
    session.add(
        Extension(
            id="com.lifelog.canvas",
            version="1.0.0",
            config={"id": "com.lifelog.canvas", "version": "1.0.0"},
        )
    )
    await session.flush()
    connection_id = uuid.uuid4()
    session.add(
        SourceConnection(
            id=connection_id,
            user_id=mock_user.id,
            extension_id="com.lifelog.canvas",
            name="Canvas",
            config={},
        )
    )
    await session.flush()
    record = SourceRecord(
        connection_id=connection_id,
        external_key="canvas:assignment:789",
        current_revision="r2",
        source_updated_at=T0,
        update_policy="replace",
    )
    session.add(record)
    await session.flush()
    raw = RawLog(
        device_id="source",
        extension_id="com.lifelog.canvas",
        payload={"due_at": "2024-02-01"},
        payload_hash="h1",
        source_record_id=record.id,
        external_key="canvas:assignment:789",
        external_revision="r2",
        source_updated_at=T0,
    )
    session.add(raw)
    await session.flush()
    session.add(Event(source_log_id=raw.id, event_type="assignment", start_time=T0))
    await session.commit()

    result = await execute_tool(
        session,
        user_id=mock_user.id,
        area_id=None,
        name="resolve_source_history",
        arguments={"external_key": "canvas:assignment:789"},
    )
    assert result["update_policy"] == "replace"
    assert result["revisions"][0]["revision"] == "r2"
    assert result["revisions"][0]["events"][0]["event_type"] == "assignment"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_propose_action_creates_review_item(session, mock_user):
    await _persist_user(session, mock_user)
    result = await execute_tool(
        session,
        user_id=mock_user.id,
        area_id=None,
        name="propose_action",
        arguments={
            "summary": "Move the essay to Thursday",
            "action": {
                "type": "reschedule_commitment",
                "commitment_title": "Essay",
                "new_due_at": "2024-01-04T18:00:00",
            },
            "consequential": True,
        },
    )
    await session.commit()
    assert result["review_item_id"]
    items = (await session.execute(select(ReviewItem))).scalars().all()
    assert len(items) == 1
    assert items[0].kind == "proposed_action"
    assert items[0].consequential is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unknown_tool_and_bad_args_are_errors(session, mock_user):
    result = await execute_tool(
        session, user_id=mock_user.id, area_id=None, name="nonsense", arguments={}
    )
    assert result["error"]

    result = await execute_tool(
        session,
        user_id=mock_user.id,
        area_id=None,
        name="traverse_graph",
        arguments={"entity_name": ""},
    )
    assert result["error"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_proposed_action_accept_reschedules_commitment(async_client, session, mock_user):
    from app.services.inbox import upsert_review_item

    await _persist_user(session, mock_user)
    commitment = Commitment(
        owner_user_id=mock_user.id,
        title="Essay draft",
        status="planned",
        due_at=_dt(10),
        data={},
    )
    session.add(commitment)
    await session.commit()

    item = await upsert_review_item(
        session,
        user_id=mock_user.id,
        kind="proposed_action",
        source_type="proposed_action",
        source_id=uuid.uuid4(),
        title="Move the essay to Thursday",
        payload={
            "action": {
                "type": "reschedule_commitment",
                "commitment_title": "Essay",
                "new_due_at": "2024-01-04T18:00:00",
            }
        },
        choices=[{"id": "accept"}, {"id": "reject"}, {"id": "dismiss"}],
    )
    await session.commit()

    response = await async_client.post(
        f"/api/v1/inbox/{item.id}/decision", json={"decision": "accept", "value": {}}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    await session.refresh(commitment)
    assert commitment.due_at == datetime(2024, 1, 4, 18, 0, 0)
    assert commitment.data["rescheduled_by"] == "proposed_action"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_chat_plans_executes_and_cites_tools(async_client, session, mock_user, monkeypatch):
    from app.services import intelligence

    await _persist_user(session, mock_user)
    course = await create_entity(session, entity_type="course", name="Calculus", owner_user_id=mock_user.id)
    event = await _event(session, "study_session", {"course_name": "Calculus", "duration": 3600}, _dt(9))
    await session.commit()
    await link_event(
        session,
        event_id=event.id,
        predicate="studied_for",
        object_id=course.id,
        object_type="entity",
        occurred_from=event.start_time,
        occurred_until=event.start_time + timedelta(hours=1),
        source_event_id=event.id,
        extractor="test",
        extraction_version=1,
    )
    await session.commit()

    calls = 0

    async def model_function(_messages, _info):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "calculate_recorded_duration",
                        {"predicate": "studied_for", "entity_name": "Calculus"},
                    )
                ]
            )
        return ModelResponse(
            parts=[TextPart("You studied Calculus for 1.0 hours [T1].")]
        )

    monkeypatch.setattr(
        intelligence,
        "_configured_model",
        lambda: (FunctionModel(model_function), "test", "function-model"),
    )

    response = await async_client.post(
        "/api/v1/ai/chat",
        json={"message": "How much did I study Calculus today?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "[T1]" in body["response"]
    assert body["context_used"] is True
    assert any(citation["id"] == "T1" for citation in body["citations"])
    tool_citation = next(c for c in body["citations"] if c["id"] == "T1")
    assert tool_citation["result"]["total_seconds"] == 3600.0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_chat_falls_back_when_tool_planning_fails(async_client, session, mock_user, monkeypatch):
    from app.services import intelligence

    await _persist_user(session, mock_user)

    async def model_function(_messages, _info):
        return ModelResponse(parts=[TextPart("Hello.")])

    monkeypatch.setattr(
        intelligence,
        "_configured_model",
        lambda: (FunctionModel(model_function), "test", "function-model"),
    )
    response = await async_client.post(
        "/api/v1/ai/chat",
        json={"message": "hello"},
    )
    assert response.status_code == 200
    assert response.json()["response"] == "Hello."

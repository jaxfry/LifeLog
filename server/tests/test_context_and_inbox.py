import uuid

import pytest
from sqlmodel import select

from app.models.captures import Capture
from app.models.config import Extension
from app.models.context import ContextLink, ReviewDecision, ReviewItem
from app.models.retrieval import SearchDocument
from app.services.inbox import suggest_entity_merges, upsert_review_item
from lifelog_sdk import PollContext, PollPage, SourceRecord, stable_revision
from lifelog_sdk.testing import assert_no_secret_echo, run_poller_contract


async def _persist_user(session, user) -> None:
    session.add(user)
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_life_area_is_many_to_many_and_enforces_scoped_privacy(
    async_client,
    session,
    mock_user,
):
    await _persist_user(session, mock_user)
    school = (await async_client.post("/api/v1/life-areas", json={"name": "School"})).json()
    work = (await async_client.post("/api/v1/life-areas", json={"name": "Work"})).json()
    captured = await async_client.post(
        "/api/v1/captures/notes",
        json={
            "text": "The capstone calculus presentation is on Friday",
            "life_area_ids": [school["id"], work["id"]],
            "privacy": {
                "visibility": "selected_areas",
                "allowed_area_ids": [school["id"]],
            },
        },
    )
    assert captured.status_code == 201
    capture_id = uuid.UUID(captured.json()["capture"]["id"])
    links = (
        await session.execute(
            select(ContextLink).where(
                ContextLink.target_type == "capture",
                ContextLink.target_id == capture_id,
            )
        )
    ).scalars().all()
    assert {str(link.life_area_id) for link in links} == {school["id"], work["id"]}
    assert len((await session.execute(select(SearchDocument))).scalars().all()) == 1

    school_search = await async_client.get(
        "/api/v1/search",
        params={"q": "capstone calculus", "life_area_id": school["id"]},
    )
    work_search = await async_client.get(
        "/api/v1/search",
        params={"q": "capstone calculus", "life_area_id": work["id"]},
    )
    assert len(school_search.json()["hits"]) == 1
    assert work_search.json()["hits"] == []
    assert len((await async_client.get(f"/api/v1/life-areas/{school['id']}/memories")).json()) == 1
    assert (await async_client.get(f"/api/v1/life-areas/{work['id']}/memories")).json() == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_inbox_classification_decision_updates_capture(
    async_client,
    session,
    mock_user,
):
    await _persist_user(session, mock_user)
    capture = Capture(
        user_id=mock_user.id,
        kind="photo",
        captured_at=mock_user.created_at,
        status="awaiting_review",
        classification={"label": "worksheet", "confidence": 0.55, "needs_review": True},
    )
    session.add(capture)
    await session.flush()
    item = await upsert_review_item(
        session,
        user_id=mock_user.id,
        kind="classification",
        source_type="capture",
        source_id=capture.id,
        capture_id=capture.id,
        title="Check this classification",
        payload={"suggested_label": "worksheet"},
    )
    await session.commit()

    pending = await async_client.get("/api/v1/inbox")
    assert [entry["id"] for entry in pending.json()] == [str(item.id)]
    decided = await async_client.post(
        f"/api/v1/inbox/{item.id}/decision",
        json={"decision": "accept", "value": {"label": "calculus assignment"}},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "accepted"
    await session.refresh(capture)
    assert capture.classification["label"] == "calculus assignment"
    assert capture.classification["source"] == "user_confirmation"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_connector_sdk_validates_paging_revisions_and_secret_hygiene():
    payload = {"course": "Calculus", "due": "2026-09-04"}
    assert stable_revision(payload) == stable_revision({"due": "2026-09-04", "course": "Calculus"})
    context = PollContext(connection_id="connection-1", secrets={"token": "top-secret"})

    async def poll(config):
        assert config["secrets"]["token"] == "top-secret"
        return PollPage(
            records=[SourceRecord.replace("assignment-1", payload)],
            next_checkpoint={"cursor": "2"},
        )

    page = await run_poller_contract(poll, context)
    assert page.records[0].external_revision == stable_revision(payload)
    assert_no_secret_echo(page, context)
    with pytest.raises(ValueError, match="has_more requires next_checkpoint"):
        PollPage(has_more=True)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_installed_connectors_expose_declarative_life_area_templates(
    async_client,
    session,
    mock_user,
):
    await _persist_user(session, mock_user)
    session.add(
        Extension(
            id="com.lifelog.canvas",
            version="1.0.0",
            config={
                "life_areas": [
                    {
                        "slug": "school",
                        "name": "School",
                        "recognition_hints": ["course", "assignment"],
                        "suggested_questions": ["What is due next?"],
                    }
                ]
            },
        )
    )
    await session.commit()
    response = await async_client.get("/api/v1/life-area-templates")
    assert response.status_code == 200
    assert response.json() == [
        {
            "extension_id": "com.lifelog.canvas",
            "slug": "school",
            "name": "School",
            "recognition_hints": ["course", "assignment"],
            "suggested_questions": ["What is due next?"],
        }
    ]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_entity_merge_suggestions_and_acceptance(async_client, session, mock_user):
    from app.services.kernel import add_entity_alias, create_entity, get_current_entity

    await _persist_user(session, mock_user)
    firefox = await create_entity(session, entity_type="application", name="Firefox", owner_user_id=mock_user.id)
    browser = await create_entity(
        session,
        entity_type="application",
        name="Firefox Browser",
        owner_user_id=mock_user.id,
    )
    await add_entity_alias(session, browser.id, "Firefox")
    await session.commit()

    assert await suggest_entity_merges(session, mock_user.id) == 1
    items = (await session.execute(select(ReviewItem))).scalars().all()
    assert len(items) == 1
    item = items[0]
    assert item.kind == "entity_merge"
    assert item.payload["merged_id"] == str(browser.id)
    assert item.payload["survivor_id"] == str(firefox.id)
    assert item.confidence == 0.85
    assert [choice["id"] for choice in item.choices] == ["accept", "reject", "dismiss"]
    await session.commit()

    decided = await async_client.post(
        f"/api/v1/inbox/{item.id}/decision", json={"decision": "accept", "value": {}}
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "accepted"

    assert await get_current_entity(session, browser.id) is None
    assert await get_current_entity(session, firefox.id) is not None
    decisions = (await session.execute(select(ReviewDecision))).scalars().all()
    assert len(decisions) == 1
    assert decisions[0].decision == "accept"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_inbox_choices_gate_decisions_and_record_history(async_client, session, mock_user):
    await _persist_user(session, mock_user)
    item = await upsert_review_item(
        session,
        user_id=mock_user.id,
        kind="entity_merge",
        source_type="entity",
        source_id=uuid.uuid4(),
        title="Merge?",
        choices=[{"id": "accept"}, {"id": "reject"}, {"id": "dismiss"}],
        confidence=0.5,
        priority="high",
    )
    await session.commit()

    bad = await async_client.post(
        f"/api/v1/inbox/{item.id}/decision", json={"decision": "maybe"}
    )
    assert bad.status_code == 409

    ok = await async_client.post(
        f"/api/v1/inbox/{item.id}/decision", json={"decision": "reject"}
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "rejected"
    await session.refresh(item)
    assert item.priority == "high"
    assert item.confidence == 0.5

    decisions = (await session.execute(select(ReviewDecision))).scalars().all()
    assert len(decisions) == 1
    assert decisions[0].decision == "reject"

    again = await async_client.post(
        f"/api/v1/inbox/{item.id}/decision", json={"decision": "dismiss"}
    )
    assert again.status_code == 409


@pytest.mark.asyncio
@pytest.mark.integration
async def test_measurement_aggregate_endpoint(async_client, session, mock_user):
    from app.models.kernel import Measurement
    from app.services.kernel import create_entity

    await _persist_user(session, mock_user)
    course = await create_entity(
        session,
        entity_type="course",
        name="CS 101",
        owner_user_id=mock_user.id,
    )
    for score in (88.0, 92.0, 96.0):
        session.add(
            Measurement(
                owner_user_id=mock_user.id,
                entity_id=course.id,
                metric="exam_score",
                value=score,
                unit="percent",
                occurred_at=mock_user.created_at,
                confidence=1.0,
            )
        )
    await session.commit()

    response = await async_client.get(
        "/api/v1/kernel/aggregates/measurement",
        params={"entity_id": str(course.id), "metric": "exam_score"},
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["entity_name"] == "CS 101"
    assert rows[0]["count"] == 3
    assert rows[0]["average"] == 92.0
    assert rows[0]["minimum"] == 88.0
    assert rows[0]["maximum"] == 96.0
    assert rows[0]["unit"] == "percent"

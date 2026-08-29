import uuid
from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlmodel import select

from app.models.ingest import Event, RawLog
from app.models.kernel import Relation


async def _seed_event(
    session,
    owner_user_id: uuid.UUID,
    event_type: str = "app_usage",
) -> Event:
    raw_log = RawLog(
        owner_user_id=owner_user_id,
        device_id="test_dev",
        extension_id="com.lifelog.aw",
        payload={"test": True},
        payload_hash=f"hash_{uuid.uuid4().hex}",
    )
    session.add(raw_log)
    await session.flush()

    event = Event(
        owner_user_id=owner_user_id,
        source_log_id=raw_log.id,
        event_type=event_type,
        start_time=datetime(2024, 1, 1, 10, 0, 0),
        data={"app": "Firefox"},
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def _create_entity(client: AsyncClient, entity_type: str, name: str) -> dict:
    response = await client.post(
        "/api/v1/kernel/entities",
        json={"entity_type": entity_type, "name": name},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_and_list_entities(mock_user, async_client: AsyncClient):
    created = await _create_entity(async_client, "person", "Alice")

    response = await async_client.get("/api/v1/kernel/entities")
    assert response.status_code == 200
    entities = response.json()
    assert any(e["id"] == created["id"] for e in entities)

    response = await async_client.get("/api/v1/kernel/entities", params={"entity_type": "person"})
    assert all(e["entity_type"] == "person" for e in response.json())


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_entity_and_history(mock_user, mock_superuser, async_client: AsyncClient):
    first = await _create_entity(async_client, "person", "Alice")
    second = await _create_entity(async_client, "person", "Alice R.")

    response = await async_client.post(
        f"/api/v1/kernel/entities/{first['id']}/supersede",
        json={"replacement_id": second["id"]},
    )
    assert response.status_code == 200

    response = await async_client.get(f"/api/v1/kernel/entities/{first['id']}")
    assert response.status_code == 404

    response = await async_client.get(f"/api/v1/kernel/entities/{first['id']}/history")
    assert response.status_code == 200
    history = response.json()
    assert len(history) == 2
    assert {e["id"] for e in history} == {first["id"], second["id"]}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_supersede_requires_superuser(mock_user, async_client: AsyncClient):
    entity = await _create_entity(async_client, "person", "Alice")

    response = await async_client.post(
        f"/api/v1/kernel/entities/{entity['id']}/supersede",
        json={"replacement_id": None},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.integration
async def test_relation_crud_and_event_link(mock_user, async_client: AsyncClient, session):
    alice = await _create_entity(async_client, "person", "Alice")
    bob = await _create_entity(async_client, "person", "Bob")

    response = await async_client.post(
        "/api/v1/kernel/relations",
        json={
            "subject_id": alice["id"],
            "subject_type": "entity",
            "predicate": "knows",
            "object_id": bob["id"],
            "object_type": "entity",
        },
    )
    assert response.status_code == 201
    relation = response.json()

    response = await async_client.get(
        "/api/v1/kernel/relations",
        params={"subject_id": alice["id"]},
    )
    assert any(r["id"] == relation["id"] for r in response.json())

    event = await _seed_event(session, mock_user.id)
    response = await async_client.post(
        f"/api/v1/kernel/events/{event.id}/relations",
        json={
            "predicate": "occurred_at",
            "object_id": bob["id"],
            "object_type": "entity",
        },
    )
    assert response.status_code == 201
    got = response.json()
    assert got["subject_id"] == str(event.id)
    assert got["subject_type"] == "event"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_relation_validation(mock_user, async_client: AsyncClient):
    alice = await _create_entity(async_client, "person", "Alice")

    response = await async_client.post(
        "/api/v1/kernel/relations",
        json={
            "subject_id": alice["id"],
            "subject_type": "entity",
            "predicate": "knows",
            "object_id": str(uuid.uuid4()),
            "object_type": "entity",
        },
    )
    assert response.status_code == 400

    response = await async_client.post(
        "/api/v1/kernel/relations",
        json={
            "subject_id": alice["id"],
            "subject_type": "entity",
            "predicate": "knows",
            "object_id": alice["id"],
            "object_type": "entity",
            "confidence": 1.1,
        },
    )
    assert response.status_code == 422

    response = await async_client.post(
        "/api/v1/kernel/relations",
        json={
            "subject_id": alice["id"],
            "subject_type": "banana",
            "predicate": "knows",
            "object_id": alice["id"],
            "object_type": "entity",
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.integration
async def test_merge_entities_via_api(mock_user, mock_superuser, async_client: AsyncClient):
    survivor = await _create_entity(async_client, "person", "Alice Smith")
    merged = await _create_entity(async_client, "person", "Alice A.")
    other = await _create_entity(async_client, "person", "Bob")

    await async_client.post(
        "/api/v1/kernel/relations",
        json={
            "subject_id": merged["id"],
            "subject_type": "entity",
            "predicate": "knows",
            "object_id": other["id"],
            "object_type": "entity",
        },
    )

    response = await async_client.post(
        "/api/v1/kernel/entities/merge",
        json={"survivor_id": survivor["id"], "merged_id": merged["id"]},
    )
    assert response.status_code == 200
    got = response.json()
    assert got["id"] == survivor["id"]
    assert str(merged["id"]) in got["data"]["merged_from_ids"]

    response = await async_client.get(f"/api/v1/kernel/entities/{merged['id']}")
    assert response.status_code == 404

    response = await async_client.get("/api/v1/kernel/relations", params={"object_id": other["id"]})
    assert any(r["subject_id"] == merged["id"] for r in response.json())

    response = await async_client.get(f"/api/v1/kernel/entities/{survivor['id']}/graph")
    assert response.status_code == 200
    graph = response.json()
    assert any(entity["id"] == survivor["id"] for entity in graph["entities"])
    assert any(relation["subject_id"] == merged["id"] for relation in graph["relations"])


@pytest.mark.asyncio
@pytest.mark.integration
async def test_supersede_event_retires_facts(mock_user, mock_superuser, async_client: AsyncClient, session):
    event = await _seed_event(session, mock_user.id)
    place = await _create_entity(async_client, "place", "Office")

    response = await async_client.post(
        f"/api/v1/kernel/events/{event.id}/relations",
        json={
            "predicate": "occurred_at",
            "object_id": place["id"],
            "object_type": "entity",
        },
    )
    assert response.status_code == 201
    relation_id = response.json()["id"]

    response = await async_client.post(
        f"/api/v1/kernel/events/{event.id}/supersede",
        json={"replacement_id": None},
    )
    assert response.status_code == 200

    result = await session.execute(
        select(Relation).where(Relation.id == uuid.UUID(relation_id))
    )
    stored = result.scalars().first()
    assert stored is not None
    assert stored.is_superseded is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_supersede_relation_via_api(mock_user, mock_superuser, async_client: AsyncClient):
    alice = await _create_entity(async_client, "person", "Alice")
    bob = await _create_entity(async_client, "person", "Bob")

    response = await async_client.post(
        "/api/v1/kernel/relations",
        json={
            "subject_id": alice["id"],
            "subject_type": "entity",
            "predicate": "knows",
            "object_id": bob["id"],
            "object_type": "entity",
        },
    )
    relation_id = response.json()["id"]

    response = await async_client.post(
        f"/api/v1/kernel/relations/{relation_id}/supersede",
        json={"replacement_id": None},
    )
    assert response.status_code == 200

    response = await async_client.get("/api/v1/kernel/relations", params={"subject_id": alice["id"]})
    assert response.json() == []

    response = await async_client.get(
        "/api/v1/kernel/relations",
        params={"subject_id": alice["id"], "include_superseded": True},
    )
    assert any(r["id"] == relation_id for r in response.json())

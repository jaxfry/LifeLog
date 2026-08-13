import uuid
from datetime import datetime

import pytest
from sqlmodel import select

from app.models.ingest import Event, RawLog
from app.models.kernel import Entity, Relation
from app.services.kernel import (
    add_entity_alias,
    create_entity,
    create_relation,
    get_current_entity,
    get_current_entity_by_name,
    get_entity_history,
    link_event,
    merge_entities,
    supersede_entity,
    supersede_event,
    supersede_relation,
)


async def _make_event(session) -> Event:
    rl = RawLog(
        device_id="test_dev",
        extension_id="test.ext",
        payload={"test": True},
        payload_hash=f"hash_{uuid.uuid4().hex}",
    )
    session.add(rl)
    await session.flush()

    event = Event(
        source_log_id=rl.id,
        event_type="app_usage",
        start_time=datetime(2024, 1, 1, 10, 0, 0),
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_entity_and_get_current(session):
    entity = await create_entity(session, entity_type="person", name="Alice")

    assert entity.name == "Alice"
    assert entity.data is None
    assert entity.confidence is None
    assert entity.is_superseded is False
    assert entity.superseded_by is None

    found = await get_current_entity(session, entity.id)
    assert found is not None
    assert found.id == entity.id

    missing = await get_current_entity(session, uuid.uuid4())
    assert missing is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_relation_to_entity(session):
    alice = await create_entity(session, entity_type="person", name="Alice")
    bob = await create_entity(session, entity_type="person", name="Bob")

    relation = await create_relation(
        session,
        subject_id=alice.id,
        subject_type="entity",
        predicate="knows",
        object_id=bob.id,
        object_type="entity",
        confidence=0.9,
    )

    result = await session.execute(select(Relation).where(Relation.id == relation.id))
    stored = result.scalars().first()
    assert stored is not None
    assert stored.subject_id == alice.id
    assert stored.subject_type == "entity"
    assert stored.predicate == "knows"
    assert stored.object_id == bob.id
    assert stored.object_type == "entity"
    assert stored.confidence == 0.9


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_relation_invalid_type_raises(session):
    alice = await create_entity(session, entity_type="person", name="Alice")
    bob = await create_entity(session, entity_type="person", name="Bob")

    with pytest.raises(ValueError):
        await create_relation(
            session,
            subject_id=alice.id,
            subject_type="relation",
            predicate="knows",
            object_id=bob.id,
            object_type="entity",
        )

    with pytest.raises(ValueError):
        await create_relation(
            session,
            subject_id=alice.id,
            subject_type="entity",
            predicate="knows",
            object_id=bob.id,
            object_type="banana",
        )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_relation_missing_id_raises(session):
    bob = await create_entity(session, entity_type="person", name="Bob")

    with pytest.raises(ValueError):
        await create_relation(
            session,
            subject_id=uuid.uuid4(),
            subject_type="entity",
            predicate="knows",
            object_id=bob.id,
            object_type="entity",
        )

    with pytest.raises(ValueError):
        await create_relation(
            session,
            subject_id=bob.id,
            subject_type="entity",
            predicate="knows",
            object_id=uuid.uuid4(),
            object_type="event",
        )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_relation_can_point_at_event(session):
    event = await _make_event(session)
    place = await create_entity(session, entity_type="place", name="Office")

    relation = await link_event(
        session,
        event_id=event.id,
        predicate="occurred_at",
        object_id=place.id,
        object_type="entity",
    )

    assert relation.subject_id == event.id
    assert relation.subject_type == "event"
    assert relation.object_id == place.id

    result = await session.execute(select(Relation).where(Relation.id == relation.id))
    stored = result.scalars().first()
    assert stored.subject_type == "event"
    assert stored.object_id == place.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_supersede_entity(session):
    original = await create_entity(session, entity_type="person", name="Alice")
    replacement = await create_entity(session, entity_type="person", name="Alice R.")

    await supersede_entity(session, original.id, replacement_id=replacement.id)

    assert await get_current_entity(session, original.id) is None
    current = await get_current_entity(session, replacement.id)
    assert current is not None
    assert current.id == replacement.id

    history = await get_entity_history(session, original.id)
    assert [e.id for e in history] == [original.id, replacement.id]
    assert history[0].is_superseded is True
    assert history[0].superseded_by == replacement.id
    assert history[1].is_superseded is False

    history_from_current = await get_entity_history(session, replacement.id)
    assert [e.id for e in history_from_current] == [original.id, replacement.id]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_supersede_relation(session):
    alice = await create_entity(session, entity_type="person", name="Alice")
    bob = await create_entity(session, entity_type="person", name="Bob")
    relation = await create_relation(
        session,
        subject_id=alice.id,
        subject_type="entity",
        predicate="knows",
        object_id=bob.id,
        object_type="entity",
    )
    replacement = await create_relation(
        session,
        subject_id=alice.id,
        subject_type="entity",
        predicate="is_friends_with",
        object_id=bob.id,
        object_type="entity",
    )

    await supersede_relation(session, relation.id, replacement_id=replacement.id)

    result = await session.execute(select(Relation).where(Relation.id == relation.id))
    stored = result.scalars().first()
    assert stored is not None
    assert stored.is_superseded is True
    assert stored.superseded_by == replacement.id
    assert stored.invalidated_at is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_supersede_relation_invalidated_at_uses_knowledge_time(session):
    alice = await create_entity(session, entity_type="person", name="Alice")
    bob = await create_entity(session, entity_type="person", name="Bob")
    relation = await create_relation(
        session,
        subject_id=alice.id,
        subject_type="entity",
        predicate="works_at",
        object_id=bob.id,
        object_type="entity",
        occurred_from=datetime(2023, 1, 1, 9, 0, 0),
    )
    replacement = await create_relation(
        session,
        subject_id=alice.id,
        subject_type="entity",
        predicate="works_at",
        object_id=bob.id,
        object_type="entity",
        occurred_from=datetime(2024, 6, 1, 9, 0, 0),
    )

    await supersede_relation(session, relation.id, replacement_id=replacement.id)

    result = await session.execute(select(Relation).where(Relation.id == relation.id))
    stored = result.scalars().first()
    assert stored.invalidated_at == replacement.created_at


@pytest.mark.asyncio
@pytest.mark.integration
async def test_merge_entities_reparents_relations(session):
    survivor = await create_entity(session, entity_type="person", name="Alice Smith")
    merged = await create_entity(session, entity_type="person", name="Alice A.")
    other = await create_entity(session, entity_type="person", name="Bob")

    r1 = await create_relation(
        session,
        subject_id=merged.id,
        subject_type="entity",
        predicate="knows",
        object_id=other.id,
        object_type="entity",
    )
    r2 = await create_relation(
        session,
        subject_id=other.id,
        subject_type="entity",
        predicate="knows",
        object_id=merged.id,
        object_type="entity",
    )

    await merge_entities(session, survivor_id=survivor.id, merged_id=merged.id)

    result = await session.execute(select(Entity).where(Entity.id == merged.id))
    merged_row = result.scalars().first()
    assert merged_row.is_superseded is True
    assert merged_row.superseded_by == survivor.id

    result = await session.execute(select(Relation).where(Relation.id == r1.id))
    assert result.scalars().first().subject_id == merged.id
    result = await session.execute(select(Relation).where(Relation.id == r2.id))
    assert result.scalars().first().object_id == merged.id

    result = await session.execute(select(Entity).where(Entity.id == survivor.id))
    survivor_row = result.scalars().first()
    assert survivor_row.data["merged_from_ids"] == [str(merged.id)]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_merge_entities_preserves_existing_data(session):
    survivor = await create_entity(
        session,
        entity_type="person",
        name="Alice Smith",
        data={"nickname": "Ali"},
    )
    merged = await create_entity(session, entity_type="person", name="Alice A.")

    await merge_entities(session, survivor_id=survivor.id, merged_id=merged.id)

    result = await session.execute(select(Entity).where(Entity.id == survivor.id))
    survivor_row = result.scalars().first()
    assert survivor_row.data["nickname"] == "Ali"
    assert survivor_row.data["merged_from_ids"] == [str(merged.id)]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_supersede_entity_self_reference_raises(session):
    entity = await create_entity(session, entity_type="person", name="Alice")

    with pytest.raises(ValueError):
        await supersede_entity(session, entity.id, replacement_id=entity.id)

    assert await get_current_entity(session, entity.id) is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_supersede_relation_self_reference_raises(session):
    alice = await create_entity(session, entity_type="person", name="Alice")
    bob = await create_entity(session, entity_type="person", name="Bob")
    relation = await create_relation(
        session,
        subject_id=alice.id,
        subject_type="entity",
        predicate="knows",
        object_id=bob.id,
        object_type="entity",
    )

    with pytest.raises(ValueError):
        await supersede_relation(session, relation.id, replacement_id=relation.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_merge_entities_same_id_raises(session):
    entity = await create_entity(session, entity_type="person", name="Alice")

    with pytest.raises(ValueError):
        await merge_entities(session, survivor_id=entity.id, merged_id=entity.id)

    assert await get_current_entity(session, entity.id) is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_supersede_missing_id_raises(session):
    with pytest.raises(ValueError):
        await supersede_entity(session, uuid.uuid4())

    with pytest.raises(ValueError):
        await supersede_relation(session, uuid.uuid4())


@pytest.mark.asyncio
@pytest.mark.integration
async def test_merge_entities_missing_id_raises(session):
    entity = await create_entity(session, entity_type="person", name="Alice")

    with pytest.raises(ValueError):
        await merge_entities(session, survivor_id=entity.id, merged_id=uuid.uuid4())

    with pytest.raises(ValueError):
        await merge_entities(session, survivor_id=uuid.uuid4(), merged_id=entity.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_entity_history_terminates_on_cycle(session):
    first = await create_entity(session, entity_type="person", name="Alice")
    second = await create_entity(session, entity_type="person", name="Alice R.")

    await supersede_entity(session, first.id, replacement_id=second.id)
    with pytest.raises(ValueError, match="cycle"):
        await supersede_entity(session, second.id, replacement_id=first.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_supersede_event_retires_derived_relations(session):
    event = await _make_event(session)
    event.end_time = datetime(2024, 1, 1, 11, 0, 0)
    await session.commit()
    place = await create_entity(session, entity_type="place", name="Office")
    relation = await link_event(
        session,
        event_id=event.id,
        predicate="occurred_at",
        object_id=place.id,
        object_type="entity",
    )

    await supersede_event(session, event.id)

    result = await session.execute(select(Relation).where(Relation.id == relation.id))
    stored = result.scalars().first()
    assert stored.is_superseded is True
    assert stored.invalidated_at is not None

    alive = await get_current_entity_by_name(session, "place", "Office")
    assert alive is not None
    assert alive.id == place.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_supersede_event_missing_id_raises(session):
    with pytest.raises(ValueError):
        await supersede_event(session, uuid.uuid4())


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_entity_by_name_case_insensitive(session):
    await create_entity(session, entity_type="application", name="Firefox")
    found = await get_current_entity_by_name(session, "application", "firefox")
    assert found is not None
    assert found.name == "Firefox"

    superseded = await get_current_entity_by_name(session, "application", "Chrome")
    assert superseded is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_entity_by_name_matches_alias(session):
    entity = await create_entity(session, entity_type="application", name="Visual Studio Code")
    await add_entity_alias(session, entity.id, "VS Code")

    found = await get_current_entity_by_name(session, "application", "VS Code")
    assert found is not None
    assert found.id == entity.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_entity_by_name_normalized_tokens(session):
    await create_entity(session, entity_type="application", name="Visual Studio Code")

    found = await get_current_entity_by_name(session, "application", "visual-studio-code")
    assert found is not None
    assert found.name == "Visual Studio Code"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_add_entity_alias_is_idempotent(session):
    entity = await create_entity(session, entity_type="application", name="Firefox")

    await add_entity_alias(session, entity.id, "Firefox")
    await add_entity_alias(session, entity.id, "Mozilla Firefox")
    await add_entity_alias(session, entity.id, "mozilla-firefox")

    result = await session.execute(select(Entity).where(Entity.id == entity.id))
    stored = result.scalars().first()
    assert stored.data["aliases"] == ["Mozilla Firefox"]

    found = await get_current_entity_by_name(session, "application", "mozilla firefox")
    assert found is not None
    assert found.id == entity.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_add_entity_alias_missing_id_raises(session):
    with pytest.raises(ValueError):
        await add_entity_alias(session, uuid.uuid4(), "Alias")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_occurred_window_round_trip(session):
    event = await _make_event(session)
    place = await create_entity(session, entity_type="place", name="Office")
    occurred_from = datetime(2024, 1, 1, 9, 0, 0)
    occurred_until = datetime(2024, 1, 1, 10, 30, 0)

    relation = await link_event(
        session,
        event_id=event.id,
        predicate="occurred_at",
        object_id=place.id,
        object_type="entity",
        occurred_from=occurred_from,
        occurred_until=occurred_until,
    )

    result = await session.execute(select(Relation).where(Relation.id == relation.id))
    stored = result.scalars().first()
    assert stored.occurred_from == occurred_from
    assert stored.occurred_until == occurred_until

import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlmodel import select

from app.models.auth import Device, User
from app.models.claims import ClaimEvidence, FactEvidence, MemoryClaim
from app.models.config import Extension
from app.models.ingest import Event, RawLog
from app.models.kernel import Entity, Measurement, Relation
from app.services.extraction import backfill_event_facts, extract_event_facts
from app.workers.process import process_log


@pytest.fixture(autouse=True)
async def extraction_device_owner(session):
    owner = User(username=f"extraction-{uuid.uuid4().hex[:8]}", hashed_password="x")
    session.add(owner)
    await session.flush()
    session.add(
        Device(
            id="test_dev",
            user_id=owner.id,
            name="Extraction test device",
            api_key_hash="x",
        )
    )
    await session.commit()
    return owner


async def _make_event(
    session,
    event_type: str,
    data: dict,
    extension_id: str = "com.lifelog.aw",
) -> Event:
    raw_log = RawLog(
        device_id="test_dev",
        extension_id=extension_id,
        payload={"test": True},
        payload_hash=f"hash_{uuid.uuid4().hex}",
    )
    session.add(raw_log)
    await session.flush()

    event = Event(
        source_log_id=raw_log.id,
        event_type=event_type,
        start_time=datetime(2024, 1, 1, 10, 0, 0),
        data=data,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def _relations_for(session, event: Event) -> list[Relation]:
    result = await session.execute(select(Relation).where(Relation.subject_id == event.id))
    return list(result.scalars().all())


async def _entity_for(session, entity_type: str) -> Entity | None:
    result = await session.execute(
        select(Entity).where(Entity.entity_type == entity_type)
    )
    return result.scalars().first()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_app_usage_extracts_facts(session):
    event = await _make_event(session, "app_usage", {"app": "Firefox", "title": "Docs"})

    entities, relations = await extract_event_facts(session, event)
    assert entities == 1
    assert relations == 1

    entity = await _entity_for(session, "application")
    assert entity is not None
    assert entity.name == "Firefox"
    assert entity.confidence == 1.0
    assert entity.canonical_key == "firefox"

    stored = await _relations_for(session, event)
    assert len(stored) == 1
    relation = stored[0]
    assert relation.predicate == "used_app"
    assert relation.subject_type == "event"
    assert relation.object_id == entity.id
    assert relation.object_type == "entity"
    assert relation.source_event_id == event.id
    assert relation.extractor == "_extract_app_usage"
    assert relation.extraction_version == 1
    assert relation.data["source_log_id"] == str(event.source_log_id)
    assert relation.occurred_from == event.start_time
    assert relation.occurred_until is None
    claim = (await session.execute(select(MemoryClaim))).scalars().one()
    assert claim.reconciliation_status == "accepted"
    assert claim.canonical_target_id == relation.id
    assert (await session.execute(select(ClaimEvidence))).scalars().one().event_id == event.id
    assert (await session.execute(select(FactEvidence))).scalars().one().claim_id == claim.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_manifest_fact_mapping_projects_extension_event(session):
    session.add(
        Extension(
            id="com.lifelog.school",
            version="1.0.0",
            config={
                "id": "com.lifelog.school",
                "version": "1.0.0",
                "fact_mappings": [
                    {
                        "event_type": "assignment_received",
                        "predicate": "for_course",
                        "object_entity_type": "course",
                        "value_path": "course.name",
                        "transform": "lowercase",
                        "confidence": 0.82,
                    }
                ],
            },
        )
    )
    await session.commit()
    event = await _make_event(
        session,
        "assignment_received",
        {"course": {"name": "CS 101"}, "title": "Essay"},
        extension_id="com.lifelog.school",
    )

    assert await extract_event_facts(session, event) == (1, 1)
    entity = await _entity_for(session, "course")
    relation = (await _relations_for(session, event))[0]
    assert entity is not None and entity.name == "cs 101"
    assert entity.confidence == 0.82
    assert relation.predicate == "for_course"
    assert relation.extractor == "manifest:com.lifelog.school:0"
    assert relation.confidence == 0.82
    assert await extract_event_facts(session, event) == (0, 0)
    assert len(await _relations_for(session, event)) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_app_usage_window_from_duration(session):
    event = await _make_event(
        session, "app_usage", {"app": "Firefox", "duration": 300.0}
    )

    entities, relations = await extract_event_facts(session, event)
    assert (entities, relations) == (1, 1)

    stored = await _relations_for(session, event)
    assert stored[0].occurred_from == event.start_time
    assert stored[0].occurred_until == datetime(2024, 1, 1, 10, 5, 0)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_app_usage_window_ignores_bad_duration(session):
    event = await _make_event(
        session, "app_usage", {"app": "Firefox", "duration": "nope"}
    )

    entities, relations = await extract_event_facts(session, event)
    assert (entities, relations) == (1, 1)

    stored = await _relations_for(session, event)
    assert stored[0].occurred_from == event.start_time
    assert stored[0].occurred_until is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_browsing_extracts_domain(session):
    event = await _make_event(
        session, "browsing", {"url": "https://www.GitHub.com/jaxon/lifelog", "title": "Repo"}
    )

    entities, relations = await extract_event_facts(session, event)
    assert entities == 1
    assert relations == 1

    entity = await _entity_for(session, "domain")
    assert entity is not None
    assert entity.name == "github.com"

    stored = await _relations_for(session, event)
    assert stored[0].predicate == "browsed"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_url_without_scheme_extracts_domain(session):
    event = await _make_event(session, "browsing", {"url": "github.com/some/path"})

    entities, relations = await extract_event_facts(session, event)
    assert entities == 1
    assert relations == 1

    entity = await _entity_for(session, "domain")
    assert entity.name == "github.com"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_extraction_is_idempotent(session):
    event = await _make_event(session, "app_usage", {"app": "Firefox"})

    entities, relations = await extract_event_facts(session, event)
    assert (entities, relations) == (1, 1)

    entities, relations = await extract_event_facts(session, event)
    assert (entities, relations) == (0, 0)

    assert len(await _relations_for(session, event)) == 1
    result = await session.execute(select(Entity).where(Entity.entity_type == "application"))
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_entity_reuse_across_events(session):
    first = await _make_event(session, "app_usage", {"app": "Firefox"})
    second = await _make_event(session, "app_usage", {"app": "firefox"})

    await extract_event_facts(session, first)
    await extract_event_facts(session, second)

    result = await session.execute(select(Entity).where(Entity.entity_type == "application"))
    entities = result.scalars().all()
    assert len(entities) == 1
    assert len(await _relations_for(session, first)) == 1
    assert len(await _relations_for(session, second)) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_variant_spelling_reuses_entity_and_records_alias(session):
    first = await _make_event(session, "app_usage", {"app": "visual-studio-code"})
    second = await _make_event(session, "app_usage", {"app": "Visual Studio Code"})

    await extract_event_facts(session, first)
    await extract_event_facts(session, second)

    result = await session.execute(select(Entity).where(Entity.entity_type == "application"))
    entities = result.scalars().all()
    assert len(entities) == 1
    assert entities[0].name == "visual-studio-code"
    assert entities[0].data["aliases"] == ["Visual Studio Code"]
    assert len(await _relations_for(session, first)) == 1
    assert len(await _relations_for(session, second)) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_distinct_spellings_stay_separate(session):
    first = await _make_event(session, "app_usage", {"app": "VS Code"})
    second = await _make_event(session, "app_usage", {"app": "Visual Studio Code"})

    await extract_event_facts(session, first)
    await extract_event_facts(session, second)

    result = await session.execute(select(Entity).where(Entity.entity_type == "application"))
    entities = result.scalars().all()
    assert len(entities) == 2
    names = {entity.name for entity in entities}
    assert names == {"VS Code", "Visual Studio Code"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unknown_event_type_is_noop(session):
    event = await _make_event(session, "device_status", {"status": "afk"})

    entities, relations = await extract_event_facts(session, event)
    assert (entities, relations) == (0, 0)
    assert await _relations_for(session, event) == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_app_usage_without_app_is_noop(session):
    event = await _make_event(session, "app_usage", {"title": "No app field"})

    entities, relations = await extract_event_facts(session, event)
    assert (entities, relations) == (0, 0)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_process_log_wires_extraction(session):
    raw_log = RawLog(
        device_id="test_dev",
        extension_id="com.lifelog.aw",
        payload={"app": "VS Code"},
        payload_hash=f"hash_{uuid.uuid4().hex}",
    )
    session.add(raw_log)
    await session.commit()

    with patch("app.workers.process.run_normalization") as mock_norm:
        mock_norm.return_value = [{"type": "app_usage", "data": {"app": "VS Code"}}]
        events = await process_log(session, raw_log.id)

    assert len(events) == 1
    assert events[0].confidence == 0.7
    entity = await _entity_for(session, "application")
    assert entity is not None
    assert entity.name == "VS Code"
    assert entity.canonical_key == "vs code"

    stored = await _relations_for(session, events[0])
    assert len(stored) == 1
    assert stored[0].predicate == "used_app"
    assert stored[0].object_id == entity.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_process_log_confidence_from_timestamp(session):
    raw_log = RawLog(
        device_id="test_dev",
        extension_id="com.lifelog.aw",
        payload={"app": "VS Code", "timestamp": "2024-01-01T12:00:00Z"},
        payload_hash=f"hash_{uuid.uuid4().hex}",
    )
    session.add(raw_log)
    await session.commit()

    with patch("app.workers.process.run_normalization") as mock_norm:
        mock_norm.return_value = [
            {"type": "app_usage", "data": {"app": "VS Code", "timestamp": "2024-01-01T12:00:00Z"}}
        ]
        events = await process_log(session, raw_log.id)

    assert len(events) == 1
    assert events[0].confidence == 1.0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_process_log_rolls_back_events_when_extraction_fails(session):
    raw_log = RawLog(
        device_id="test_dev",
        extension_id="com.lifelog.aw",
        payload={"app": "VS Code"},
        payload_hash=f"hash_{uuid.uuid4().hex}",
    )
    session.add(raw_log)
    await session.commit()

    with (
        patch("app.workers.process.run_normalization") as mock_norm,
        patch("app.workers.process.extract_event_facts", side_effect=RuntimeError("extractor failed")),
    ):
        mock_norm.return_value = [{"type": "app_usage", "data": {"app": "VS Code"}}]
        with pytest.raises(RuntimeError, match="extractor failed"):
            await process_log(session, raw_log.id)

    events = (
        await session.execute(select(Event).where(Event.source_log_id == raw_log.id))
    ).scalars().all()
    assert events == []
    await session.refresh(raw_log)
    assert raw_log.processing_status == "failed"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_process_log_retry_is_idempotent(session):
    raw_log = RawLog(
        device_id="test_dev",
        extension_id="com.lifelog.aw",
        payload={"app": "VS Code"},
        payload_hash=f"hash_{uuid.uuid4().hex}",
    )
    session.add(raw_log)
    await session.commit()

    with patch("app.workers.process.run_normalization") as mock_norm:
        mock_norm.return_value = [{"type": "app_usage", "data": {"app": "VS Code"}}]
        first = await process_log(session, raw_log.id)
        second = await process_log(session, raw_log.id)

    assert [event.id for event in second] == [event.id for event in first]
    stored = (
        await session.execute(select(Event).where(Event.source_log_id == raw_log.id))
    ).scalars().all()
    assert len(stored) == 1
    assert len(await _relations_for(session, stored[0])) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_memory_backfill_marks_events_that_produce_no_facts(session):
    event = await _make_event(session, "app_usage", {"title": "Missing app"})

    first = await backfill_event_facts(session)
    second = await backfill_event_facts(session)

    assert first["events_processed"] == 1
    assert first["relations_created"] == 0
    assert second["events_processed"] == 0
    await session.refresh(event)
    assert event.memory_extraction_version == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_entity_mapping_resolves_identity_aliases_and_metadata(session):
    session.add(
        Extension(
            id="com.lifelog.school",
            version="1.1.0",
            config={
                "id": "com.lifelog.school",
                "version": "1.1.0",
                "entity_mappings": [
                    {
                        "event_type": "course_enrollment",
                        "entity_ref": "course",
                        "entity_type": "course",
                        "name_path": "course.name",
                        "identity_path": "course.external_id",
                        "aliases_path": "course.aliases",
                        "metadata_paths": {"code": "course.code", "term": "course.term"},
                    }
                ],
            },
        )
    )
    await session.commit()
    event = await _make_event(
        session,
        "course_enrollment",
        {
            "course": {
                "name": "Linear Algebra",
                "external_id": "canvas:course:42",
                "code": "MATH 210",
                "term": "Spring 2026",
                "aliases": ["LA", "MATH210"],
            }
        },
        extension_id="com.lifelog.school",
    )

    assert await extract_event_facts(session, event) == (1, 0)
    entity = await _entity_for(session, "course")
    assert entity is not None
    assert entity.name == "Linear Algebra"
    assert entity.data["external_identity"] == "canvas:course:42"
    assert entity.data["metadata"] == {"code": "MATH 210", "term": "Spring 2026"}
    assert set(entity.data["aliases"]) == {"LA", "MATH210"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_relation_mapping_projects_entity_to_entity_relations(session):
    session.add(
        Extension(
            id="com.lifelog.school",
            version="1.2.0",
            config={
                "id": "com.lifelog.school",
                "version": "1.2.0",
                "entity_mappings": [
                    {
                        "event_type": "assignment",
                        "entity_ref": "assignment",
                        "entity_type": "assignment",
                        "name_path": "title",
                    },
                    {
                        "event_type": "assignment",
                        "entity_ref": "course",
                        "entity_type": "course",
                        "name_path": "course.name",
                    },
                ],
                "relation_mappings": [
                    {
                        "event_type": "assignment",
                        "subject": "entity",
                        "subject_entity_ref": "assignment",
                        "predicate": "for_course",
                        "object": "entity",
                        "object_entity_ref": "course",
                    },
                    {
                        "event_type": "assignment",
                        "subject": "record",
                        "predicate": "is_assignment",
                        "object": "entity",
                        "object_entity_ref": "assignment",
                    },
                ],
            },
        )
    )
    await session.commit()
    event = await _make_event(
        session,
        "assignment",
        {"title": "Essay 1", "course": {"name": "CS 101"}},
        extension_id="com.lifelog.school",
    )

    entities, relations = await extract_event_facts(session, event)
    assert entities == 2
    assert relations == 2

    result = await session.execute(select(Relation).where(Relation.source_event_id == event.id))
    stored = list(result.scalars().all())
    entity_subject = [r for r in stored if r.subject_type == "entity"]
    event_subject = [r for r in stored if r.subject_type == "event"]
    assert len(entity_subject) == 1
    assert entity_subject[0].predicate == "for_course"
    assert entity_subject[0].object_type == "entity"
    assert entity_subject[0].extractor == "manifest:com.lifelog.school:relation:0"
    assert len(event_subject) == 1
    assert event_subject[0].predicate == "is_assignment"

    assert await extract_event_facts(session, event) == (0, 0)
    assert len((await session.execute(select(Relation))).scalars().all()) == 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_measurement_mapping_writes_numeric_facts(session):
    session.add(
        Extension(
            id="com.lifelog.school",
            version="1.3.0",
            config={
                "id": "com.lifelog.school",
                "version": "1.3.0",
                "entity_mappings": [
                    {
                        "event_type": "grade",
                        "entity_ref": "course",
                        "entity_type": "course",
                        "name_path": "course.name",
                    }
                ],
                "measurement_mappings": [
                    {
                        "event_type": "grade",
                        "entity_ref": "course",
                        "metric": "score",
                        "value_path": "score",
                        "unit_path": "score_unit",
                    }
                ],
            },
        )
    )
    await session.commit()
    event = await _make_event(
        session,
        "grade",
        {"course": {"name": "CS 101"}, "score": 92.5, "score_unit": "percent"},
        extension_id="com.lifelog.school",
    )

    entities, relations = await extract_event_facts(session, event)
    assert (entities, relations) == (1, 0)

    measurements = (await session.execute(select(Measurement))).scalars().all()
    assert len(measurements) == 1
    assert measurements[0].metric == "score"
    assert measurements[0].value == 92.5
    assert measurements[0].unit == "percent"
    assert measurements[0].source_event_id == event.id
    assert measurements[0].extractor == "manifest:com.lifelog.school:measurement:0"

    assert await extract_event_facts(session, event) == (0, 0)
    assert len((await session.execute(select(Measurement))).scalars().all()) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_measurement_mapping_skips_non_numeric_values(session):
    session.add(
        Extension(
            id="com.lifelog.school",
            version="1.4.0",
            config={
                "id": "com.lifelog.school",
                "version": "1.4.0",
                "entity_mappings": [
                    {
                        "event_type": "grade",
                        "entity_ref": "course",
                        "entity_type": "course",
                        "name_path": "course.name",
                    }
                ],
                "measurement_mappings": [
                    {
                        "event_type": "grade",
                        "entity_ref": "course",
                        "metric": "score",
                        "value_path": "score",
                    }
                ],
            },
        )
    )
    await session.commit()
    event = await _make_event(
        session,
        "grade",
        {"course": {"name": "CS 101"}, "score": "excused"},
        extension_id="com.lifelog.school",
    )

    assert await extract_event_facts(session, event) == (1, 0)
    assert (await session.execute(select(Measurement))).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_text_measurement_mapping_stores_string_values(session):
    session.add(
        Extension(
            id="com.lifelog.school",
            version="1.5.0",
            config={
                "id": "com.lifelog.school",
                "version": "1.5.0",
                "entity_mappings": [
                    {
                        "event_type": "health_log",
                        "entity_ref": "self",
                        "entity_type": "person",
                        "name_path": "person.name",
                    }
                ],
                "measurement_mappings": [
                    {
                        "event_type": "health_log",
                        "entity_ref": "self",
                        "metric": "mood",
                        "value_path": "mood",
                        "value_type": "text",
                    }
                ],
            },
        )
    )
    await session.commit()
    event = await _make_event(
        session,
        "health_log",
        {"person": {"name": "Me"}, "mood": "focused"},
        extension_id="com.lifelog.school",
    )

    entities, relations = await extract_event_facts(session, event)
    assert (entities, relations) == (1, 0)
    measurements = (await session.execute(select(Measurement))).scalars().all()
    assert len(measurements) == 1
    assert measurements[0].value is None
    assert measurements[0].value_text == "focused"
    assert measurements[0].metric == "mood"

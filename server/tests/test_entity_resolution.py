from datetime import datetime

import pytest
from sqlmodel import select

from app.models.auth import User
from app.models.config import Extension
from app.models.context import ContextLink, LifeArea, MemoryPolicy, ReviewItem
from app.models.ingest import Event, RawLog
from app.models.retrieval import SearchDocument
from app.services.context import set_policy, target_visible
from app.services.inbox import decide_review_item, suggest_entity_merges, suggest_entity_merges_for
from app.services.kernel import (
    create_entity,
    create_relation,
    entity_family_ids,
    get_current_entity_by_name,
    merge_entities,
    resolve_current_entity,
    reverse_entity_merge,
)
from app.services.measurements import aggregate_measurements, create_measurement
from app.services.retrieval import graph_context


async def _user(session, mock_user) -> None:
    session.add(mock_user)
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_prefix_containment_suggests_calc12(session, mock_user):
    await _user(session, mock_user)
    await create_entity(session, entity_type="course", name="Calculus 12", owner_user_id=mock_user.id)
    await create_entity(session, entity_type="course", name="calc 12", owner_user_id=mock_user.id)
    await session.commit()

    assert await suggest_entity_merges(session, mock_user.id) == 1
    items = (await session.execute(select(ReviewItem))).scalars().all()
    assert len(items) == 1
    assert items[0].confidence == 0.9
    assert items[0].payload["matched"] == "prefix-containment"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_near_typo_suggests_calulus(session, mock_user):
    await _user(session, mock_user)
    await create_entity(session, entity_type="course", name="Calculus 12", owner_user_id=mock_user.id)
    await create_entity(session, entity_type="course", name="Calulus 12", owner_user_id=mock_user.id)
    await session.commit()

    assert await suggest_entity_merges(session, mock_user.id) == 1
    item = (await session.execute(select(ReviewItem))).scalars().one()
    assert item.confidence == 0.95


@pytest.mark.asyncio
@pytest.mark.integration
async def test_section_qualifiers_never_suggest(session, mock_user):
    await _user(session, mock_user)
    await create_entity(session, entity_type="course", name="Physics 101", owner_user_id=mock_user.id)
    await create_entity(session, entity_type="course", name="Physics 101 Lab", owner_user_id=mock_user.id)
    await create_entity(session, entity_type="course", name="Physics 101 Discussion", owner_user_id=mock_user.id)
    await session.commit()

    assert await suggest_entity_merges(session, mock_user.id) == 0
    assert (await session.execute(select(ReviewItem))).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unrelated_and_generic_names_never_suggest(session, mock_user):
    await _user(session, mock_user)
    await create_entity(session, entity_type="application", name="Firefox", owner_user_id=mock_user.id)
    await create_entity(session, entity_type="application", name="Chrome", owner_user_id=mock_user.id)
    await create_entity(session, entity_type="application", name="notes", owner_user_id=mock_user.id)
    await create_entity(session, entity_type="application", name="Note", owner_user_id=mock_user.id)
    await session.commit()

    assert await suggest_entity_merges(session, mock_user.id) == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cross_type_never_suggests(session, mock_user):
    await _user(session, mock_user)
    await create_entity(session, entity_type="application", name="Firefox", owner_user_id=mock_user.id)
    await create_entity(session, entity_type="course", name="Firefox", owner_user_id=mock_user.id)
    await session.commit()

    assert await suggest_entity_merges(session, mock_user.id) == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_identical_names_create_review_candidate_without_becoming_identity(
    session, mock_user
):
    await _user(session, mock_user)
    first = await create_entity(
        session, entity_type="course", name="Calculus 12", owner_user_id=mock_user.id
    )
    second = await create_entity(
        session, entity_type="course", name="Calculus 12", owner_user_id=mock_user.id
    )
    await session.commit()

    assert first.id != second.id
    assert await suggest_entity_merges(session, mock_user.id) == 1
    item = (await session.execute(select(ReviewItem))).scalars().one()
    assert item.payload["matched"] == "canonical-key:calculus 12"
    assert item.confidence == 0.99


@pytest.mark.asyncio
@pytest.mark.integration
async def test_rejected_pair_is_never_resent(session, mock_user):
    await _user(session, mock_user)
    await create_entity(session, entity_type="course", name="Calculus 12", owner_user_id=mock_user.id)
    await create_entity(session, entity_type="course", name="calc 12", owner_user_id=mock_user.id)
    await session.commit()

    assert await suggest_entity_merges(session, mock_user.id) == 1
    item = (await session.execute(select(ReviewItem))).scalars().one()
    await decide_review_item(session, item, "reject")
    await session.commit()

    assert await suggest_entity_merges(session, mock_user.id) == 0
    assert len((await session.execute(select(ReviewItem))).scalars().all()) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_real_time_suggestion_for_single_entity(session, mock_user):
    await _user(session, mock_user)
    calculus = await create_entity(session, entity_type="course", name="Calculus 12", owner_user_id=mock_user.id)
    fragment = await create_entity(session, entity_type="course", name="calc 12", owner_user_id=mock_user.id)
    await session.commit()

    assert await suggest_entity_merges_for(session, mock_user.id, fragment.id) == 1
    items = (await session.execute(select(ReviewItem))).scalars().all()
    assert len(items) == 1
    assert items[0].payload["survivor_id"] == str(calculus.id)
    assert items[0].payload["merged_id"] == str(fragment.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_accept_merge_fixes_future_resolution(session, mock_user):
    await _user(session, mock_user)
    calculus = await create_entity(session, entity_type="course", name="Calculus 12")
    fragment = await create_entity(session, entity_type="course", name="calc 12")
    await session.commit()

    await merge_entities(session, survivor_id=calculus.id, merged_id=fragment.id)
    await session.commit()

    found = await get_current_entity_by_name(session, "course", "calc 12")
    assert found is not None
    assert found.id == calculus.id
    assert await resolve_current_entity(session, fragment.id) is not None
    assert (await resolve_current_entity(session, fragment.id)).id == calculus.id
    assert fragment.id in await entity_family_ids(session, calculus.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_merged_external_identity_keeps_resolving_to_survivor(session, mock_user):
    await _user(session, mock_user)
    calculus = await create_entity(
        session,
        entity_type="course",
        name="Calculus 12",
        owner_user_id=mock_user.id,
        identity_namespace="source-connection:canvas",
        external_identity="course:primary",
    )
    fragment = await create_entity(
        session,
        entity_type="course",
        name="calc 12",
        owner_user_id=mock_user.id,
        identity_namespace="source-connection:canvas",
        external_identity="course:legacy",
    )
    await session.commit()

    await merge_entities(
        session,
        survivor_id=calculus.id,
        merged_id=fragment.id,
        decided_by_user_id=mock_user.id,
    )
    await session.commit()

    found = await get_current_entity_by_name(
        session,
        "course",
        "name is intentionally irrelevant",
        owner_user_id=mock_user.id,
        identity_namespace="source-connection:canvas",
        external_identity="course:legacy",
    )
    assert found is not None
    assert found.id == calculus.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_merge_folds_measurements_and_search_documents(session, mock_user):
    await _user(session, mock_user)
    calculus = await create_entity(session, entity_type="course", name="Calculus 12")
    fragment = await create_entity(session, entity_type="course", name="calc 12")
    await create_measurement(
        session,
        entity_id=fragment.id,
        metric="score",
        value=88.0,
        occurred_at=datetime(2024, 1, 1),
    )
    await session.commit()

    await merge_entities(session, survivor_id=calculus.id, merged_id=fragment.id)
    await session.commit()

    merged_doc = (
        await session.execute(
            select(SearchDocument).where(
                SearchDocument.source_type == "entity",
                SearchDocument.source_id == fragment.id,
            )
        )
    ).scalars().all()
    assert all(document.is_superseded for document in merged_doc)

    survivor_doc = (
        await session.execute(
            select(SearchDocument).where(
                SearchDocument.source_type == "entity",
                SearchDocument.source_id == calculus.id,
                SearchDocument.is_superseded == False,
            )
        )
    ).scalars().first()
    assert survivor_doc is not None
    assert "calc 12" in survivor_doc.content

    rows = await aggregate_measurements(session, entity_id=calculus.id, metric="score")
    assert rows[0]["average"] == 88.0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_duration_aggregate_folds_merged_family(session, mock_user):
    await _user(session, mock_user)
    calculus = await create_entity(session, entity_type="course", name="Calculus 12")
    fragment = await create_entity(session, entity_type="course", name="calc 12")
    raw = RawLog(device_id="d", extension_id="e", payload={}, payload_hash="h1")
    session.add(raw)
    await session.flush()
    event = Event(
        source_log_id=raw.id,
        event_type="study_session",
        start_time=datetime(2024, 1, 1, 9, 0, 0),
    )
    session.add(event)
    await session.flush()
    await create_relation(
        session,
        subject_id=event.id,
        subject_type="event",
        predicate="studied_for",
        object_id=fragment.id,
        object_type="entity",
        occurred_from=datetime(2024, 1, 1, 9, 0, 0),
        occurred_until=datetime(2024, 1, 1, 10, 0, 0),
    )
    await session.commit()

    await merge_entities(session, survivor_id=calculus.id, merged_id=fragment.id)
    await session.commit()

    from app.services.kernel import aggregate_duration

    rows = await aggregate_duration(
        session, entity_id=calculus.id, predicate="studied_for"
    )
    assert len(rows) == 1
    assert rows[0]["name"] == "Calculus 12"
    assert rows[0]["seconds"] == 3600.0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_graph_context_resolves_superseded_endpoints(session, mock_user):
    await _user(session, mock_user)
    calculus = await create_entity(session, entity_type="course", name="Calculus 12")
    fragment = await create_entity(session, entity_type="course", name="calc 12")
    await session.commit()
    await merge_entities(session, survivor_id=calculus.id, merged_id=fragment.id)
    raw = RawLog(device_id="d", extension_id="e", payload={}, payload_hash="h2")
    session.add(raw)
    await session.flush()
    event = Event(
        source_log_id=raw.id,
        event_type="study_session",
        start_time=datetime(2024, 1, 1, 9, 0, 0),
    )
    session.add(event)
    await session.flush()
    await create_relation(
        session,
        subject_id=event.id,
        subject_type="event",
        predicate="studied_for",
        object_id=fragment.id,
        object_type="entity",
    )
    await session.commit()

    facts = await graph_context(session, "Calculus 12", limit=10)
    assert any(fact["predicate"] == "studied_for" and fact["object"] == "Calculus 12" for fact in facts)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_extraction_triggers_real_time_suggestion(session, mock_user):
    """The demo scenario: a sloppy 'calc 12' event raises an Inbox suggestion."""
    from app.services.extraction import extract_event_facts

    await _user(session, mock_user)
    await create_entity(session, entity_type="course", name="Calculus 12", owner_user_id=mock_user.id)
    session.add(
        Extension(
            id="com.lifelog.school",
            version="1.0.0",
            config={
                "id": "com.lifelog.school",
                "version": "1.0.0",
                "entity_mappings": [
                    {
                        "event_type": "study_session",
                        "entity_ref": "course",
                        "entity_type": "course",
                        "name_path": "course_name",
                    }
                ],
            },
        )
    )
    await session.commit()
    raw = RawLog(
        owner_user_id=mock_user.id,
        device_id="macbook",
        extension_id="com.lifelog.school",
        payload={"kind": "study"},
        payload_hash="h3",
    )
    session.add(raw)
    await session.flush()
    event = Event(
        owner_user_id=mock_user.id,
        source_log_id=raw.id,
        event_type="study_session",
        start_time=datetime(2024, 1, 1, 9, 0, 0),
        data={"course_name": "calc 12"},
    )
    session.add(event)
    await session.commit()

    await extract_event_facts(session, event)
    await session.commit()

    items = (await session.execute(select(ReviewItem))).scalars().all()
    assert len(items) == 1
    assert items[0].kind == "entity_merge"
    assert items[0].confidence == 0.9


@pytest.mark.asyncio
@pytest.mark.integration
async def test_merge_reparents_context_links(session, mock_user):
    await _user(session, mock_user)
    survivor = await create_entity(session, entity_type="course", name="Calculus 12")
    merged = await create_entity(session, entity_type="course", name="calc 12")
    area = LifeArea(user_id=mock_user.id, slug="school", name="School")
    session.add(area)
    await session.flush()
    session.add(
        ContextLink(
            life_area_id=area.id,
            target_type="entity",
            target_id=merged.id,
            source="recognition_rule",
        )
    )
    await session.commit()

    await merge_entities(session, survivor_id=survivor.id, merged_id=merged.id)
    await session.commit()

    links = (
        await session.execute(
            select(ContextLink).where(
                ContextLink.target_type == "entity", ContextLink.target_id == survivor.id
            )
        )
    ).scalars().all()
    assert len(links) == 1
    assert links[0].life_area_id == area.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_same_name_external_identities_remain_distinct(session, mock_user):
    await _user(session, mock_user)
    first = await create_entity(
        session,
        "course",
        "Biology 101",
        owner_user_id=mock_user.id,
        identity_namespace="canvas:school-a",
        external_identity="course-1",
    )
    second = await create_entity(
        session,
        "course",
        "Biology 101",
        owner_user_id=mock_user.id,
        identity_namespace="canvas:school-a",
        external_identity="course-2",
    )
    await session.commit()
    assert first.id != second.id
    found = await get_current_entity_by_name(
        session,
        "course",
        "Biology 101",
        owner_user_id=mock_user.id,
        identity_namespace="canvas:school-a",
        external_identity="course-2",
    )
    assert found is not None and found.id == second.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_merge_suggestions_and_approval_are_owner_scoped(session, mock_user):
    await _user(session, mock_user)
    other = User(username="other-owner", hashed_password="x")
    session.add(other)
    await session.flush()
    ours = await create_entity(
        session, "course", "Calculus 12", owner_user_id=mock_user.id
    )
    theirs = await create_entity(
        session, "course", "calc 12", owner_user_id=other.id
    )
    await session.commit()
    assert await suggest_entity_merges(session, mock_user.id) == 0

    item = ReviewItem(
        user_id=mock_user.id,
        kind="entity_merge",
        source_type="entity_merge_pair",
        source_id=ours.id,
        title="malicious merge",
        payload={"survivor_id": str(ours.id), "merged_id": str(theirs.id)},
        choices=[{"id": "accept"}],
    )
    session.add(item)
    await session.flush()
    with pytest.raises(ValueError, match="same owner"):
        await decide_review_item(session, item, "accept")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_merge_preserves_privacy_metadata_and_can_reverse(session, mock_user):
    await _user(session, mock_user)
    survivor = await create_entity(
        session,
        "course",
        "Calculus 12",
        data={"teacher": "Ms Green"},
        owner_user_id=mock_user.id,
    )
    merged = await create_entity(
        session,
        "course",
        "calc 12",
        data={"teacher": "Mr Blue", "room": "204"},
        owner_user_id=mock_user.id,
    )
    area = LifeArea(user_id=mock_user.id, slug="school", name="School")
    session.add(area)
    await session.flush()
    session.add(ContextLink(life_area_id=area.id, target_type="entity", target_id=merged.id))
    await set_policy(
        session,
        mock_user.id,
        "entity",
        merged.id,
        visibility="private",
    )
    await session.commit()

    merge = await merge_entities(
        session,
        survivor.id,
        merged.id,
        decided_by_user_id=mock_user.id,
    )
    await session.commit()
    policy = (
        await session.execute(
            select(MemoryPolicy).where(
                MemoryPolicy.target_type == "entity",
                MemoryPolicy.target_id == survivor.id,
                MemoryPolicy.user_id == mock_user.id,
            )
        )
    ).scalars().one()
    assert policy.visibility == "private"
    assert survivor.data["room"] == "204"
    assert survivor.data["attribute_conflicts"]["teacher"][0]["value"] == "Mr Blue"
    assert not await target_visible(
        session,
        user_id=mock_user.id,
        target_type="entity",
        target_id=survivor.id,
        area_id=area.id,
    )

    await reverse_entity_merge(session, merge.id, decided_by_user_id=mock_user.id)
    await session.commit()
    await session.refresh(merged)
    await session.refresh(survivor)
    assert merged.is_superseded is False
    assert survivor.data == {"teacher": "Ms Green"}
    survivor_policy = (
        await session.execute(
            select(MemoryPolicy).where(
                MemoryPolicy.target_type == "entity",
                MemoryPolicy.target_id == survivor.id,
            )
        )
    ).scalars().first()
    assert survivor_policy is None
    restored_link = (
        await session.execute(
            select(ContextLink).where(ContextLink.target_id == merged.id)
        )
    ).scalars().one()
    assert restored_link.life_area_id == area.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_each_merge_candidate_pair_gets_its_own_review_item(session, mock_user):
    await _user(session, mock_user)
    for name in ("Calculus 12", "calc 12", "calculus12"):
        await create_entity(session, "course", name, owner_user_id=mock_user.id)
    await session.commit()
    count = await suggest_entity_merges(session, mock_user.id)
    items = (await session.execute(select(ReviewItem))).scalars().all()
    assert count == len(items)
    assert len(items) >= 2
    assert len({item.source_id for item in items}) == len(items)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_scoped_measurements_fold_merged_family_and_enforce_policy(session, mock_user):
    await _user(session, mock_user)
    survivor = await create_entity(
        session, "course", "Calculus 12", owner_user_id=mock_user.id
    )
    merged = await create_entity(
        session, "course", "calc 12", owner_user_id=mock_user.id
    )
    area = LifeArea(user_id=mock_user.id, slug="school", name="School")
    session.add(area)
    await session.flush()
    session.add(ContextLink(life_area_id=area.id, target_type="entity", target_id=merged.id))
    await set_policy(
        session,
        mock_user.id,
        "entity",
        survivor.id,
        visibility="selected_areas",
        allowed_area_ids=[area.id],
    )
    await set_policy(
        session,
        mock_user.id,
        "entity",
        merged.id,
        visibility="selected_areas",
        allowed_area_ids=[area.id],
    )
    await create_measurement(
        session,
        entity_id=merged.id,
        metric="score",
        value=88,
        occurred_at=datetime(2024, 1, 1),
    )
    await session.commit()
    await merge_entities(
        session,
        survivor.id,
        merged.id,
        decided_by_user_id=mock_user.id,
    )
    await session.commit()

    rows = await aggregate_measurements(
        session,
        entity_id=survivor.id,
        metric="score",
        area_id=area.id,
        user_id=mock_user.id,
    )
    assert rows[0]["average"] == 88

    await set_policy(
        session,
        mock_user.id,
        "entity",
        survivor.id,
        visibility="private",
    )
    assert await aggregate_measurements(
        session,
        entity_id=survivor.id,
        metric="score",
        area_id=area.id,
        user_id=mock_user.id,
    ) == []

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlmodel import select

from app.models.auth import User
from app.models.claims import EntityMention, EntityResolutionDecision, FactEvidence, MemoryClaim
from app.models.context import ReviewItem
from app.models.evidence import EvidenceDocument, EvidenceSpan
from app.models.files import Commitment, FileAttachment
from app.models.ingest import Event, RawLog
from app.models.intelligence import DerivationAttempt, DerivationRun, DirtyScope
from app.models.kernel import Entity
from app.models.processing import Session, TimelineEntry
from app.services.derivations import complete_derivation, start_derivation
from app.services.entity_resolution import reject_candidate, resolve_mention
from app.services.inbox import decide_review_item
from app.services.kernel import create_entity
from app.services.query_planning import QueryIntent, plan_query
from app.services.reconciliation import reconcile_claim
from app.services.tools import execute_tool


def _user(name: str) -> User:
    return User(username=f"{name}-{uuid.uuid4().hex[:8]}", hashed_password="x")


async def _evidence(session, owner: User, text: str) -> EvidenceSpan:
    document = EvidenceDocument(
        owner_user_id=owner.id,
        kind="note",
        full_text=text,
        source_content_hash=uuid.uuid4().hex,
        parser="test",
        parser_version="1",
        derivation_key=uuid.uuid4().hex,
    )
    session.add(document)
    await session.flush()
    span = EvidenceSpan(
        document_id=document.id,
        sequence=0,
        text=text,
        char_start=0,
        char_end=len(text),
        content_hash=uuid.uuid4().hex,
    )
    session.add(span)
    await session.flush()
    return span


@pytest.mark.asyncio
@pytest.mark.integration
async def test_file_routes_fail_closed_across_owners(
    async_client: AsyncClient,
    session,
    mock_user,
):
    other = _user("other")
    session.add(other)
    await session.flush()
    attachment = FileAttachment(
        owner_user_id=other.id,
        filename="private.txt",
        stored_path="private",
        mime_type="text/plain",
        content_hash=uuid.uuid4().hex,
    )
    session.add(attachment)
    await session.commit()

    metadata = await async_client.get(f"/api/v1/files/{attachment.id}")
    listing = await async_client.get("/api/v1/files/")

    assert metadata.status_code == 404
    assert all(item["id"] != str(attachment.id) for item in listing.json())


@pytest.mark.asyncio
@pytest.mark.integration
async def test_derivation_is_idempotent_and_attempts_are_append_only(session):
    owner = _user("derivation")
    session.add(owner)
    await session.flush()
    target_id = uuid.uuid4()
    run, attempt, should_run = await start_derivation(
        session,
        owner_user_id=owner.id,
        purpose="test",
        target_type="capture",
        target_id=target_id,
        inputs={"value": 1},
        processor="test.processor",
        processor_version="1",
        ontology_version="1",
    )
    assert should_run is True
    await complete_derivation(session, run, attempt, output_refs={"ok": True})
    repeated, _skipped_attempt, should_run = await start_derivation(
        session,
        owner_user_id=owner.id,
        purpose="test",
        target_type="capture",
        target_id=target_id,
        inputs={"value": 1},
        processor="test.processor",
        processor_version="1",
        ontology_version="1",
    )
    assert should_run is False
    assert repeated.id == run.id
    assert len((await session.execute(select(DerivationRun))).scalars().all()) == 1
    attempts = (await session.execute(select(DerivationAttempt))).scalars().all()
    assert [(item.attempt, item.status) for item in attempts] == [(1, "completed")]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_resolution_is_owner_scoped_and_explainable(session):
    owner = _user("owner")
    other = _user("other")
    session.add_all([owner, other])
    await session.flush()
    expected = await create_entity(session, "course", "Calculus 12", owner_user_id=owner.id)
    await create_entity(session, "course", "Calculus 12", owner_user_id=other.id)
    span = await _evidence(session, owner, "Calculus 12")
    mention = EntityMention(
        owner_user_id=owner.id,
        span_id=span.id,
        surface_text="Calculus 12",
        normalized_text="calculus 12",
        entity_type="course",
        extractor="test",
        extraction_version=1,
        ontology_version="1",
        derivation_key=uuid.uuid4().hex,
    )
    session.add(mention)
    await session.flush()

    resolved = await resolve_mention(
        session,
        owner_user_id=owner.id,
        mention_id=mention.id,
    )

    assert resolved is not None and resolved.id == expected.id
    assert mention.resolution_status == "resolved"
    decision = (await session.execute(select(EntityResolutionDecision))).scalars().one()
    assert decision.outcome == "accepted"
    assert decision.components["owner_match"] == 1.0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ambiguous_entity_resolution_can_be_completed_from_the_inbox(session):
    owner = _user("ambiguous-owner")
    session.add(owner)
    await session.flush()
    first = Entity(
        owner_user_id=owner.id,
        entity_type="person",
        name="Alex",
        canonical_key="alex",
    )
    second = Entity(
        owner_user_id=owner.id,
        entity_type="person",
        name="Alex",
        canonical_key="alex",
    )
    session.add_all([first, second])
    await session.flush()
    span = await _evidence(session, owner, "Alex")
    mention = EntityMention(
        owner_user_id=owner.id,
        span_id=span.id,
        surface_text="Alex",
        normalized_text="alex",
        entity_type="person",
        extractor="test",
        extraction_version=1,
        ontology_version="1",
        derivation_key=uuid.uuid4().hex,
    )
    session.add(mention)
    await session.flush()

    assert await resolve_mention(
        session,
        owner_user_id=owner.id,
        mention_id=mention.id,
    ) is None
    review = (await session.execute(select(ReviewItem))).scalars().one()
    await decide_review_item(
        session,
        review,
        str(first.id),
    )

    assert review.status == "accepted"
    assert mention.resolution_status == "resolved"
    assert mention.resolved_entity_id == first.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_rejected_identity_candidate_constrains_future_matching(session):
    owner = _user("identity-constraint")
    session.add(owner)
    await session.flush()
    first = Entity(
        owner_user_id=owner.id,
        entity_type="person",
        name="Sam",
        canonical_key="sam",
    )
    second = Entity(
        owner_user_id=owner.id,
        entity_type="person",
        name="Sam",
        canonical_key="sam",
    )
    session.add_all([first, second])
    await session.flush()
    span = await _evidence(session, owner, "Sam")
    mention = EntityMention(
        owner_user_id=owner.id,
        span_id=span.id,
        surface_text="Sam",
        normalized_text="sam",
        entity_type="person",
        extractor="test",
        extraction_version=1,
        ontology_version="1",
        derivation_key=uuid.uuid4().hex,
    )
    session.add(mention)
    await session.flush()
    await resolve_mention(session, owner_user_id=owner.id, mention_id=mention.id)
    assert await reject_candidate(
        session,
        owner_user_id=owner.id,
        mention_id=mention.id,
        candidate_entity_id=first.id,
    )

    next_span = await _evidence(session, owner, "Sam appears again")
    next_mention = EntityMention(
        owner_user_id=owner.id,
        span_id=next_span.id,
        surface_text="Sam",
        normalized_text="sam",
        entity_type="person",
        extractor="test",
        extraction_version=1,
        ontology_version="1",
        derivation_key=uuid.uuid4().hex,
    )
    session.add(next_mention)
    await session.flush()

    resolved = await resolve_mention(
        session,
        owner_user_id=owner.id,
        mention_id=next_mention.id,
    )
    assert resolved is not None and resolved.id == second.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_conflicting_claims_create_one_review_and_dirty_scope(session):
    owner = _user("claims")
    session.add(owner)
    await session.flush()
    entity = await create_entity(session, "assignment", "Essay", owner_user_id=owner.id)
    accepted = MemoryClaim(
        owner_user_id=owner.id,
        kind="attribute",
        subject_entity_id=entity.id,
        predicate="scheduled_for",
        value={"due_at": "2026-09-01T15:00:00"},
        quality_score=0.95,
        reconciliation_status="accepted",
        extractor="test",
        extraction_version=1,
        ontology_version="1",
        derivation_key=uuid.uuid4().hex,
    )
    conflicting = MemoryClaim(
        owner_user_id=owner.id,
        kind="attribute",
        subject_entity_id=entity.id,
        predicate="scheduled_for",
        value={"due_at": "2026-09-03T15:00:00"},
        quality_score=0.95,
        extractor="test",
        extraction_version=1,
        ontology_version="1",
        derivation_key=uuid.uuid4().hex,
    )
    session.add_all([accepted, conflicting])
    await session.flush()

    result = await reconcile_claim(
        session,
        owner_user_id=owner.id,
        claim_id=conflicting.id,
    )

    assert result is not None and result.reconciliation_status == "conflicting"
    reviews = (await session.execute(select(ReviewItem))).scalars().all()
    assert len(reviews) == 1 and reviews[0].user_id == owner.id
    scopes = (await session.execute(select(DirtyScope))).scalars().all()
    assert len(scopes) == 1 and scopes[0].owner_user_id == owner.id
    await decide_review_item(session, reviews[0], "keep_existing")
    assert reviews[0].status == "rejected"
    assert conflicting.reconciliation_status == "rejected"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_commitment_reconciliation_compares_identity_not_every_subjectless_claim(
    session,
):
    owner = _user("commitment-claims")
    session.add(owner)
    await session.flush()

    async def claim(title: str, due_at: str) -> MemoryClaim:
        item = MemoryClaim(
            owner_user_id=owner.id,
            kind="commitment",
            predicate="scheduled_for",
            value={"title": title, "due_at": due_at},
            quality_score=0.95,
            extractor="test",
            extraction_version=1,
            ontology_version="1",
            derivation_key=uuid.uuid4().hex,
        )
        session.add(item)
        await session.flush()
        result = await reconcile_claim(
            session,
            owner_user_id=owner.id,
            claim_id=item.id,
        )
        assert result is not None
        return result

    essay = await claim("Submit essay", "2026-09-01T15:00:00")
    lab = await claim("Submit lab", "2026-09-01T15:00:00")
    changed_essay = await claim("Submit essay", "2026-09-03T15:00:00")

    assert essay.reconciliation_status == "accepted"
    assert lab.reconciliation_status == "accepted"
    assert changed_essay.reconciliation_status == "conflicting"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_accepting_new_conflicting_deadline_projects_only_after_review(session):
    owner = _user("deadline-review")
    session.add(owner)
    await session.flush()
    old_commitment = Commitment(
        owner_user_id=owner.id,
        title="Submit essay",
        due_at=datetime(2026, 9, 1, 15),
        status="planned",
    )
    session.add(old_commitment)
    await session.flush()
    old_claim = MemoryClaim(
        owner_user_id=owner.id,
        kind="commitment",
        predicate="scheduled_for",
        value={"title": "Submit essay", "due_at": "2026-09-01T15:00:00"},
        quality_score=0.95,
        reconciliation_status="accepted",
        extractor="test",
        extraction_version=1,
        ontology_version="1",
        derivation_key=uuid.uuid4().hex,
        canonical_target_type="commitment",
        canonical_target_id=old_commitment.id,
    )
    session.add(old_claim)
    await session.flush()
    session.add(
        FactEvidence(
            target_type="commitment",
            target_id=old_commitment.id,
            claim_id=old_claim.id,
        )
    )
    new_claim = MemoryClaim(
        owner_user_id=owner.id,
        kind="commitment",
        predicate="scheduled_for",
        value={"title": "Submit essay", "due_at": "2026-09-03T15:00:00"},
        quality_score=0.95,
        extractor="test",
        extraction_version=1,
        ontology_version="1",
        derivation_key=uuid.uuid4().hex,
    )
    session.add(new_claim)
    await session.flush()

    await reconcile_claim(session, owner_user_id=owner.id, claim_id=new_claim.id)
    review = (
        await session.execute(
            select(ReviewItem).where(ReviewItem.source_id == new_claim.id)
        )
    ).scalars().one()
    assert new_claim.canonical_target_id is None

    await decide_review_item(session, review, "accept_new")

    assert review.status == "accepted"
    assert old_claim.reconciliation_status == "superseded"
    assert old_commitment.status == "cancelled"
    assert new_claim.reconciliation_status == "accepted"
    replacement = await session.get(Commitment, new_claim.canonical_target_id)
    assert replacement is not None
    assert replacement.due_at == datetime(2026, 9, 3, 15)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_query_plan_uses_deterministic_aggregate_for_longitudinal_question():
    plan = plan_query("How has my sleep changed over the past month?")
    assert QueryIntent.AGGREGATE in plan.intents
    assert QueryIntent.TEMPORAL in plan.intents
    assert plan.needs_deterministic_computation is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_evidence_tool_cannot_inspect_another_owner(session):
    owner = _user("evidence")
    other = _user("other-evidence")
    session.add_all([owner, other])
    await session.flush()
    span = await _evidence(session, other, "private evidence")

    result = await execute_tool(
        session,
        user_id=owner.id,
        area_id=None,
        name="inspect_evidence",
        arguments={"source_id": str(span.id)},
    )

    assert "error" in result


@pytest.mark.asyncio
@pytest.mark.integration
async def test_legacy_read_and_search_routes_filter_before_returning_candidates(
    async_client: AsyncClient,
    session,
    mock_user,
):
    other = _user("route-owner")
    session.add(other)
    await session.flush()
    now = datetime.now(UTC).replace(tzinfo=None)
    log = RawLog(
        owner_user_id=other.id,
        device_id="other-device",
        extension_id="other-extension",
        payload={"secret": "route-secret"},
        payload_hash=uuid.uuid4().hex,
    )
    session.add(log)
    await session.flush()
    session.add(
        Event(
            owner_user_id=other.id,
            source_log_id=log.id,
            event_type="route-secret",
            start_time=now,
            data={"secret": "route-secret"},
        )
    )
    session.add(
        Session(
            owner_user_id=other.id,
            start_time=now,
            end_time=now,
            status="completed",
        )
    )
    session.add(
        TimelineEntry(
            owner_user_id=other.id,
            start_time=now,
            end_time=now,
            activity="route-secret",
        )
    )
    session.add(
        FileAttachment(
            owner_user_id=other.id,
            filename="route-secret.txt",
            stored_path="route-secret",
            mime_type="text/plain",
            content_hash=uuid.uuid4().hex,
        )
    )
    await session.commit()

    logs = await async_client.get("/api/v1/logs")
    events = await async_client.get("/api/v1/events")
    sessions = await async_client.get("/api/v1/sessions")
    search = await async_client.get("/api/v1/search", params={"q": "route-secret"})
    stats = await async_client.get("/api/v1/analytics/stats")

    assert logs.status_code == events.status_code == sessions.status_code == 200
    assert all(item["owner_user_id"] != str(other.id) for item in logs.json())
    assert all(item["owner_user_id"] != str(other.id) for item in events.json())
    assert all(item["owner_user_id"] != str(other.id) for item in sessions.json())
    assert search.json()["timeline"] == []
    assert search.json()["files"] == []
    assert stats.json()["total_events"] == 0

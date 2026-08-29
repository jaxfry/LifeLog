import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

from app.models.retrieval import ProcessingFailure, SearchDocument
from app.services.failures import record_processing_failure
from app.services.kernel import create_entity
from app.services.retrieval import retrieve, upsert_search_document


@pytest.mark.asyncio
@pytest.mark.integration
async def test_lexical_recall_survives_without_embedding_provider(session):
    source_id = uuid.uuid4()
    with patch(
        "app.services.retrieval.embedding_with_fallback",
        AsyncMock(side_effect=RuntimeError("not configured")),
    ):
        document = await upsert_search_document(
            session,
            source_type="event",
            source_id=source_id,
            title="Calculus class",
            content="Worked on derivatives and the chain rule",
        )
    assert document.embedding is None
    hits = await retrieve(session, "chain rule")
    assert hits[0].source_id == source_id
    assert hits[0].reasons == ["lexical"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_recall_applies_explicit_temporal_scope(session):
    old_id = uuid.uuid4()
    current_id = uuid.uuid4()
    for source_id, logical_date in ((old_id, "2026-08-11"), (current_id, "2026-08-12")):
        await upsert_search_document(
            session,
            source_type="timeline",
            source_id=source_id,
            title="Calculus",
            content="Calculus practice problems",
            occurred_at=datetime.fromisoformat(f"{logical_date}T16:00:00"),
            logical_date=logical_date,
        )

    hits = await retrieve(
        session,
        "calculus",
        logical_from="2026-08-12",
        logical_until="2026-08-13",
        occurred_from=datetime(2026, 8, 12),
        occurred_until=datetime(2026, 8, 13),
    )

    assert [hit.source_id for hit in hits] == [current_id]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_agent_recall_fails_closed_without_matching_owner(session, mock_user):
    owned_id = uuid.uuid4()
    await upsert_search_document(
        session,
        source_type="capture",
        source_id=owned_id,
        content="private calculus note",
        metadata={"owner_user_id": str(mock_user.id)},
    )
    await upsert_search_document(
        session,
        source_type="capture",
        source_id=uuid.uuid4(),
        content="private calculus note from someone else",
        metadata={"owner_user_id": str(uuid.uuid4())},
    )
    await upsert_search_document(
        session,
        source_type="capture",
        source_id=uuid.uuid4(),
        content="unowned legacy calculus note",
    )

    hits = await retrieve(
        session,
        "calculus",
        user_id=mock_user.id,
        require_owner_metadata=True,
    )

    assert [hit.source_id for hit in hits] == [owned_id]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_processing_failure_is_durable_and_counts_retries(session):
    source_id = uuid.uuid4()
    await record_processing_failure(
        session,
        source_type="raw_log",
        source_id=source_id,
        stage="normalization",
        error=ValueError("bad payload"),
    )
    await record_processing_failure(
        session,
        source_type="raw_log",
        source_id=source_id,
        stage="normalization",
        error=ValueError("still bad"),
    )
    failure = (await session.execute(select(ProcessingFailure))).scalars().one()
    assert failure.attempts == 2
    assert failure.error_message == "still bad"
    assert "ValueError" in (failure.traceback or "")
    assert (await session.execute(select(SearchDocument))).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_entity_is_indexed_on_write(session):
    entity = await create_entity(
        session,
        entity_type="course",
        name="Calculus 12",
        data={"teacher": "Dr. Rivera"},
    )
    document = (
        await session.execute(
            select(SearchDocument).where(
                SearchDocument.source_type == "entity",
                SearchDocument.source_id == entity.id,
            )
        )
    ).scalars().one()
    assert document.title == "Calculus 12"
    assert document.metadata_["entity_type"] == "course"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reupsert_merges_projection_metadata(session):
    source_id = uuid.uuid4()
    original = await upsert_search_document(
        session,
        source_type="event",
        source_id=source_id,
        content="First",
        metadata={"extension_id": "school"},
    )
    original.embedding = [0.0] * 768
    original.embedding_model = "test-model"
    session.add(original)
    await session.flush()
    document = await upsert_search_document(
        session,
        source_type="event",
        source_id=source_id,
        content="Updated",
        metadata={"event_type": "lesson"},
    )
    assert document.metadata_ == {"extension_id": "school", "event_type": "lesson"}
    assert document.embedding is None
    assert document.embedding_model is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_postgres_hybrid_recall_uses_cosine_and_lexical_fusion(session, monkeypatch):
    if session.bind is None or session.bind.dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL with pgvector")

    lexical = await upsert_search_document(
        session,
        source_type="event",
        source_id=uuid.uuid4(),
        title="Calculus notes",
        content="calculus derivative practice",
    )
    lexical.embedding = [-1.0, *([0.0] * 767)]
    semantic = await upsert_search_document(
        session,
        source_type="event",
        source_id=uuid.uuid4(),
        title="Related concept",
        content="rates of change and tangent slopes",
    )
    semantic.embedding = [1.0, *([0.0] * 767)]
    session.add(lexical)
    session.add(semantic)
    await session.commit()

    monkeypatch.setattr("app.services.retrieval.settings.HACK_CLUB_AI_API_KEY", "test-key")
    with patch(
        "app.services.retrieval.embedding_with_fallback",
        AsyncMock(return_value=[1.0, *([0.0] * 767)]),
    ):
        hits = await retrieve(session, "calculus", limit=5)

    by_id = {hit.source_id: hit for hit in hits}
    assert "lexical" in by_id[lexical.source_id].reasons
    assert "semantic" in by_id[semantic.source_id].reasons

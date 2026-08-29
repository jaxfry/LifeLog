from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.models.processing import TimelineEntry
from app.services.kernel import create_entity, create_relation


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_endpoint(async_client: AsyncClient, session, mock_superuser, mock_user):
    # Create a timeline entry with a specific keyword
    t1 = TimelineEntry(
        owner_user_id=mock_user.id,
        start_time=_now(),
        end_time=_now(),
        activity="Coding in Python",
        notes="Implementing search functionality",
        category="Work",
        tags=["coding", "python"],
    )
    session.add(t1)

    # Create a file attachment with a matching keyword
    from app.models.files import FileAttachment

    f1 = FileAttachment(
        owner_user_id=mock_user.id,
        filename="project-notes.txt",
        stored_path="ab/cd/hash123",
        mime_type="text/plain",
        content_hash="hash123",
        description="Notes about the LifeLog dashboard",
        category="Docs",
    )
    session.add(f1)

    await session.commit()

    # Test keyword search over timeline
    response = await async_client.get("/api/v1/search", params={"q": "Python"})
    assert response.status_code == 200
    data = response.json()

    assert "timeline" in data
    assert "files" in data
    found = any(item["id"] == str(t1.id) for item in data["timeline"])
    assert found

    # Test search over files
    response = await async_client.get("/api/v1/search", params={"q": "LifeLog"})
    assert response.status_code == 200
    data = response.json()
    found = any(item["id"] == str(f1.id) for item in data["files"])
    assert found

    # Test no-match query
    response = await async_client.get("/api/v1/search", params={"q": "NonexistentXYZ"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["timeline"]) == 0
    assert len(data["files"]) == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_reports_actual_mode_and_graph_fact_shape(
    async_client: AsyncClient,
    session,
    mock_user,
):
    course = await create_entity(
        session, "course", "CS 101", owner_user_id=mock_user.id
    )
    assignment = await create_entity(
        session, "assignment", "Graph Essay", owner_user_id=mock_user.id
    )
    await create_relation(
        session,
        subject_id=assignment.id,
        subject_type="entity",
        predicate="for_course",
        object_id=course.id,
        object_type="entity",
        confidence=1.0,
    )
    await session.commit()

    response = await async_client.get("/api/v1/search", params={"q": "CS 101"})
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "lexical_graph"
    assert any(hit["source_type"] == "entity" for hit in data["hits"])
    assert data["graph_facts"][0] == {
        "subject": "Graph Essay",
        "predicate": "for_course",
        "object": "CS 101",
        "occurred_from": None,
        "occurred_until": None,
        "confidence": 1.0,
        "source_event_id": None,
        "source_file_id": None,
        "source_chunk_id": None,
    }

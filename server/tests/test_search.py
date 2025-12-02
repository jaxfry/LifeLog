import pytest
from httpx import AsyncClient
from app.models.data import Timeline, DailyChapter, Session, SessionStatus
from datetime import datetime, timezone
import uuid
from unittest.mock import patch, AsyncMock
import numpy as np

# Create a fake embedding of the correct dimension (768)
def fake_embedding():
    """Generate a random 768-dimensional embedding for testing."""
    return list(np.random.rand(768).astype(np.float32))

@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_endpoint(async_client: AsyncClient, session, mock_superuser):
    # Create a session first
    s1 = Session(
        id=uuid.uuid4(),
        start_time=datetime.now(timezone.utc).replace(tzinfo=None),
        end_time=datetime.now(timezone.utc).replace(tzinfo=None),
        status=SessionStatus.PROCESSED,
        timezone="UTC"
    )
    session.add(s1)
    
    # Create a timeline entry with a specific keyword (using fake embedding)
    t1 = Timeline(
        session_id=s1.id,
        start_time=datetime.now(timezone.utc).replace(tzinfo=None),
        end_time=datetime.now(timezone.utc).replace(tzinfo=None),
        activity="Coding in Python",
        notes="Implementing search functionality",
        category="Work",
        tags=["coding", "python"],
        embedding=fake_embedding()
    )
    session.add(t1)
    
    # Create a chapter with a specific keyword (using fake embedding)
    c1 = DailyChapter(
        date=datetime.now(timezone.utc).replace(tzinfo=None),
        start_time=datetime.now(timezone.utc).replace(tzinfo=None),
        end_time=datetime.now(timezone.utc).replace(tzinfo=None),
        title="Deep Work Session",
        summary="Focused on backend development",
        category="Work",
        tags=["deep work"],
        embedding=fake_embedding()
    )
    session.add(c1)
    
    await session.commit()

    # Test Keyword Search
    response = await async_client.get("/api/v1/search/", params={"q": "Python"})
    assert response.status_code == 200
    data = response.json()
    
    # Should find the timeline entry
    assert len(data["timeline"]) >= 1
    found_t1 = False
    for t in data["timeline"]:
        if t["activity"] == "Coding in Python":
            found_t1 = True
            break
    assert found_t1

    # Test Vector Search (Semantic)
    # "Programming" is semantically related to "Coding"
    response = await async_client.get("/api/v1/search/", params={"q": "Programming"})
    assert response.status_code == 200
    data = response.json()
    
    # Check that the response structure is correct
    assert "timeline" in data
    assert "chapters" in data


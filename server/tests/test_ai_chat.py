"""
Tests for the AI chat endpoint.
"""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.files import ContentChunk, FileAttachment


@pytest.mark.asyncio
async def test_ai_chat_health_not_configured(async_client: AsyncClient):
    """Test AI health check when not configured."""
    response = await async_client.get("/api/v1/ai/chat/health")
    assert response.status_code == 200
    data = response.json()
    assert "configured" in data
    assert "model" in data


@pytest.mark.asyncio
async def test_ai_chat_requires_message(mock_user, async_client: AsyncClient):
    """Test that chat endpoint requires a message."""
    response = await async_client.post("/api/v1/ai/chat", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ai_chat_accepts_valid_request(mock_user, async_client: AsyncClient):
    """Test that chat endpoint accepts valid request structure."""
    with patch("app.api.ai_chat.call_llm", AsyncMock(return_value="Hello")):
        response = await async_client.post("/api/v1/ai/chat", json={"message": "Hello", "context_days": 7})
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ai_chat_returns_grounded_artifact_citations(mock_user, async_client: AsyncClient, session):
    attachment = FileAttachment(
        filename="lecture.txt",
        stored_path="unused",
        mime_type="text/plain",
        content_hash="lecture-citation",
        processing_status="ready",
    )
    session.add(attachment)
    await session.flush()
    session.add(
        ContentChunk(
            file_id=attachment.id,
            sequence=0,
            content="Photosynthesis converts light energy into chemical energy.",
            content_type="transcript",
        )
    )
    await session.commit()

    with patch("app.api.ai_chat.call_llm", AsyncMock(return_value="It converts light energy [S1].")):
        response = await async_client.post(
            "/api/v1/ai/chat",
            json={"message": "What does photosynthesis do?"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["citations"][0]["filename"] == "lecture.txt"
    assert data["citations"][0]["id"] == "S1"

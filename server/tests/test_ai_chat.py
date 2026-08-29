"""
Tests for the AI chat endpoint.
"""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.intelligence import IntelligenceResult


def _result(response: str = "Hello", citations: list[dict] | None = None) -> IntelligenceResult:
    return IntelligenceResult(
        response=response,
        citations=citations or [],
        tools_used=[],
        usage={"requests": 1, "tool_calls": 0, "input_tokens": 10, "output_tokens": 2},
    )


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
    assistant = AsyncMock(return_value=_result())
    with patch("app.api.ai_chat.run_interactive_assistant", assistant):
        response = await async_client.post("/api/v1/ai/chat", json={"message": "Hello", "context_days": 7})
    assert response.status_code == 200
    assert response.json()["retrieval"]["time_scope"] == "chosen by assistant from the question"
    assert assistant.await_count == 1


@pytest.mark.asyncio
async def test_ai_chat_supplies_history_as_continuity_not_evidence(
    mock_user,
    async_client: AsyncClient,
):
    assistant = AsyncMock(return_value=_result("A grounded follow-up"))
    with patch("app.api.ai_chat.run_interactive_assistant", assistant):
        response = await async_client.post(
            "/api/v1/ai/chat",
            json={
                "message": "What about that topic?",
                "history": [
                    {"role": "user", "content": "Tell me about calculus"},
                    {"role": "assistant", "content": "We discussed derivatives [S1]."},
                ],
            },
        )

    assert response.status_code == 200
    assert assistant.await_args.kwargs["history"] == [
        ("user", "Tell me about calculus"),
        ("assistant", "We discussed derivatives [S1]."),
    ]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ai_chat_returns_grounded_citations(mock_user, async_client: AsyncClient):
    citation = {
        "id": "S1",
        "source_type": "artifact_chunk",
        "source_id": "evidence-id",
        "title": "lecture.txt",
        "content": "Photosynthesis converts light energy.",
    }
    assistant = AsyncMock(
        return_value=_result("It converts light energy [S1].", [citation])
    )
    with patch("app.api.ai_chat.run_interactive_assistant", assistant):
        response = await async_client.post(
            "/api/v1/ai/chat",
            json={"message": "What does photosynthesis do?"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["citations"][0]["title"] == "lecture.txt"
    assert data["citations"][0]["id"] == "S1"

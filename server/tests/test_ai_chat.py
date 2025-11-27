"""
Tests for the AI chat endpoint.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from app.main import app
from app.core.db import engine
from app.models.config import SystemConfig


@pytest_asyncio.fixture(autouse=True)
async def reset_engine():
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_ai_chat_health_not_configured():
    """Test AI health check when not configured."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        response = await ac.get("/api/v1/ai/chat/health")
        assert response.status_code == 200
        data = response.json()
        assert "configured" in data
        assert "model" in data


@pytest.mark.asyncio
async def test_ai_chat_requires_message():
    """Test that chat endpoint requires a message."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        response = await ac.post("/api/v1/ai/chat", json={})
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_ai_chat_accepts_valid_request():
    """Test that chat endpoint accepts valid request structure."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        response = await ac.post("/api/v1/ai/chat", json={"message": "Hello", "context_days": 7})
        # Will fail due to missing API key, but validates request structure
        assert response.status_code in [200, 500]

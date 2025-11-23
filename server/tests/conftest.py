"""
Shared test fixtures and configuration for pytest.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.db import engine

@pytest_asyncio.fixture(autouse=True)
async def cleanup_engine():
    """Cleanup database engine after each test."""
    yield
    await engine.dispose()

@pytest_asyncio.fixture
async def async_client():
    """Create an async HTTP client for testing."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

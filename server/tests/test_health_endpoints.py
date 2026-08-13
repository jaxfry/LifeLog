"""
Comprehensive tests for health check endpoints.
"""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
@pytest.mark.unit
async def test_health_check_basic(async_client):
    """Test basic health check endpoint."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_liveness_check(async_client):
    """Test liveness check endpoint."""
    response = await async_client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_readiness_check_healthy(async_client):
    """Test readiness check when all dependencies are healthy."""
    response = await async_client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "redis" in data


from app.core.database import get_session


@pytest.mark.asyncio
@pytest.mark.unit
async def test_readiness_check_database_failure():
    """Test readiness check when database is unavailable."""

    async def mock_get_session_failure():
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("Database connection error")
        yield mock_session

    app.dependency_overrides[get_session] = mock_get_session_failure

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
            response = await ac.get("/api/v1/health/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["database"] == "unreachable"
    finally:
        app.dependency_overrides = {}


@pytest.mark.asyncio
@pytest.mark.unit
async def test_readiness_check_redis_failure():
    """Test readiness check when Redis is unavailable."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        with patch("redis.asyncio.from_url") as mock_redis:
            # Mock Redis failure
            mock_redis_instance = AsyncMock()
            mock_redis_instance.ping.side_effect = Exception("Redis connection error")
            mock_redis_instance.aclose = AsyncMock()
            mock_redis.return_value = mock_redis_instance

            response = await ac.get("/api/v1/health/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["redis"] == "unreachable"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_health_endpoints_return_json(async_client):
    """Test that all health endpoints return JSON."""
    endpoints = ["/api/v1/health", "/api/v1/health/live"]

    for endpoint in endpoints:
        response = await async_client.get(endpoint)
        assert response.headers["content-type"] == "application/json"
        data = response.json()
        assert isinstance(data, dict)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_health_check_no_authentication_required(async_client):
    """Test that health checks don't require authentication."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200

    response = await async_client.get("/api/v1/health/live")
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.integration
async def test_readiness_check_structure(async_client):
    """Test the structure of readiness check response."""
    response = await async_client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] in ["ready", "degraded"]
    assert data["database"] in ["ok", "unreachable"]
    assert data["redis"] in ["ok", "unreachable"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_health_endpoints_performance(async_client):
    """Test that health endpoints respond quickly."""
    import time

    endpoints = ["/api/v1/health", "/api/v1/health/live"]

    for endpoint in endpoints:
        start = time.time()
        response = await async_client.get(endpoint)
        duration = time.time() - start

        assert response.status_code == 200
        assert duration < 5.0, f"{endpoint} took {duration}s to respond"

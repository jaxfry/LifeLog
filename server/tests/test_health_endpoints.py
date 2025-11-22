"""
Comprehensive tests for health check endpoints.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_health_check_basic(async_client):
    """Test basic health check endpoint."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "LifeLog"
    assert "version" in data


@pytest.mark.asyncio
async def test_liveness_check(async_client):
    """Test liveness check endpoint."""
    response = await async_client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"
    assert data["service"] == "LifeLog"


@pytest.mark.asyncio
async def test_readiness_check_healthy(async_client):
    """Test readiness check when all dependencies are healthy."""
    response = await async_client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "checks" in data
    assert "database" in data["checks"]
    assert "redis" in data["checks"]


@pytest.mark.asyncio
async def test_readiness_check_database_failure():
    """Test readiness check when database is unavailable."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("app.api.health.get_session") as mock_session:
            # Mock database failure
            mock_session.return_value.__aenter__.return_value.execute.side_effect = Exception("Database connection error")
            
            response = await ac.get("/api/v1/health/ready")
            data = response.json()
            
            assert "checks" in data
            # The endpoint will still return 200 but with not ready status
            assert data["checks"]["database"] == "unhealthy"


@pytest.mark.asyncio
async def test_readiness_check_redis_failure():
    """Test readiness check when Redis is unavailable."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("app.api.health.Redis.from_url") as mock_redis:
            # Mock Redis failure
            mock_redis.return_value.ping = AsyncMock(side_effect=Exception("Redis connection error"))
            
            response = await ac.get("/api/v1/health/ready")
            data = response.json()
            
            assert "checks" in data
            # Redis failure should be reported
            assert data["checks"]["redis"] == "unhealthy"


@pytest.mark.asyncio
async def test_health_endpoints_return_json(async_client):
    """Test that all health endpoints return JSON."""
    endpoints = ["/api/v1/health", "/api/v1/health/live", "/api/v1/health/ready"]
    
    for endpoint in endpoints:
        response = await async_client.get(endpoint)
        assert response.headers["content-type"] == "application/json"
        # Ensure it's valid JSON
        data = response.json()
        assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_health_check_no_authentication_required(async_client):
    """Test that health checks don't require authentication."""
    # Health endpoints should be publicly accessible
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    
    response = await async_client.get("/api/v1/health/live")
    assert response.status_code == 200
    
    response = await async_client.get("/api/v1/health/ready")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_readiness_check_structure(async_client):
    """Test the structure of readiness check response."""
    response = await async_client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "status" in data
    assert data["status"] in ["ready", "not ready"]
    
    assert "checks" in data
    assert isinstance(data["checks"], dict)
    
    # Verify checks structure
    for check_name, check_status in data["checks"].items():
        assert check_status in ["healthy", "unhealthy", "unknown"]


@pytest.mark.asyncio
async def test_health_endpoints_performance(async_client):
    """Test that health endpoints respond quickly."""
    import time
    
    endpoints = ["/api/v1/health", "/api/v1/health/live", "/api/v1/health/ready"]
    
    for endpoint in endpoints:
        start = time.time()
        response = await async_client.get(endpoint)
        duration = time.time() - start
        
        assert response.status_code == 200
        # Health checks should be fast (under 5 seconds)
        assert duration < 5.0, f"{endpoint} took {duration}s to respond"

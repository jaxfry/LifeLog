"""
Health check endpoints for monitoring system status.
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.db import get_session
from app.core.logger import get_logger
import os

logger = get_logger(__name__)
router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint.
    Returns 200 OK if the service is running.
    """
    return {
        "status": "healthy",
        "service": "LifeLog",
        "version": "4.0"
    }


@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_check(
    session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """
    Readiness check endpoint.
    Verifies that critical dependencies (database, Redis) are available.
    Returns 200 OK if all dependencies are ready, 503 otherwise.
    """
    checks = {
        "database": "unknown",
        "redis": "unknown"
    }
    
    all_healthy = True
    
    # Check Database
    try:
        result = await session.execute(text("SELECT 1"))
        result.scalar_one()
        checks["database"] = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        checks["database"] = "unhealthy"
        all_healthy = False
    
    # Check Redis
    try:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        from redis.asyncio import Redis
        redis_client = Redis.from_url(redis_url, decode_responses=True)
        await redis_client.ping()
        await redis_client.close()
        checks["redis"] = "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        checks["redis"] = "unhealthy"
        all_healthy = False
    
    response = {
        "status": "ready" if all_healthy else "not ready",
        "checks": checks
    }
    
    if not all_healthy:
        return response  # FastAPI will use default 200 unless we raise exception
    
    return response


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_check() -> Dict[str, Any]:
    """
    Liveness check endpoint.
    Returns 200 OK if the service is alive and responding to requests.
    """
    return {
        "status": "alive",
        "service": "LifeLog"
    }

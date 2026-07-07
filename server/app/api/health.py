import os

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import text

from app.core.database import get_session

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/live")
async def liveness():
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(session: AsyncSession = Depends(get_session)):
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    redis_ok = True
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379")
        )
        await r.ping()
        await r.aclose()
    except Exception:
        redis_ok = False

    return {
        "status": "ready" if db_ok and redis_ok else "degraded",
        "database": "ok" if db_ok else "unreachable",
        "redis": "ok" if redis_ok else "unreachable",
    }

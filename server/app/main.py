import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import auth, devices, health, ingest
from app.core.config import settings
from app.core.database import async_session_factory, close_db, init_db
from app.core.logger import get_logger, setup_logging
from app.core.rate_limit import limiter

setup_logging(log_level=settings.LOG_LEVEL, log_file=settings.LOG_FILE)
logger = get_logger(__name__)


async def _run_scheduled_sessionizer():
    """APScheduler job: run the processing pipeline."""
    async with async_session_factory() as session:
        from app.services.processing import run_processing_pipeline

        result = await run_processing_pipeline(session)
        if result["sessions_created"] or result["sessions_marked_dirty"]:
            logger.info("Scheduled processing: %s", result)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting LifeLog server...")

    await init_db()
    logger.info("Database initialized")

    arq_pool = None
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        arq_pool = await create_pool(
            RedisSettings.from_dsn(settings.REDIS_URL, retry_on_start=False),
        )
        app.state.arq_pool = arq_pool
        logger.info("Connected to Redis")
    except Exception:
        logger.warning("Redis unavailable — background workers disabled")

    scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            _run_scheduled_sessionizer,
            "interval",
            minutes=settings.SESSIONIZER_INTERVAL_MINUTES,
            id="sessionizer",
            replace_existing=True,
        )
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info(
            "Scheduler started (sessionizer every %d min)",
            settings.SESSIONIZER_INTERVAL_MINUTES,
        )
    except Exception:
        logger.warning("Scheduler unavailable")

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
    if arq_pool is not None:
        await arq_pool.close()
        logger.info("Redis connection closed")
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.ALLOWED_HOSTS.split(","),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(devices.router, prefix="/api/v1", tags=["devices"])
app.include_router(ingest.router, prefix="/api/v1", tags=["ingestion"])

if not settings.SECRET_KEY or settings.SECRET_KEY == "change-this-to-a-random-secret-key":
    if not settings.DEBUG:
        raise RuntimeError(
            "SECRET_KEY must be set in production. "
            "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    logger.warning("Using default SECRET_KEY — not suitable for production")


@app.get("/")
async def root():
    return {
        "message": "LifeLog API",
        "version": settings.APP_VERSION,
    }

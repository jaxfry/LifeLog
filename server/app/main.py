from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import (
    admin,
    ai_chat,
    analytics,
    auth,
    captures,
    client,
    commitments,
    data,
    devices,
    extensions,
    files,
    health,
    inbox,
    ingest,
    kernel,
    life_areas,
    search,
    sources,
    summaries,
    timeline,
)
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


async def _run_scheduled_timeline():
    """APScheduler job: generate timeline entries for pending sessions."""
    async with async_session_factory() as session:
        from app.services.timeline import process_pending_sessions

        count = await process_pending_sessions(session)
        if count:
            logger.info("Timeline: generated %d entries", count)


async def _run_scheduled_summary():
    """APScheduler job: generate an isolated daily summary for each owner."""
    async with async_session_factory() as session:
        from sqlmodel import select

        from app.models.processing import TimelineEntry
        from app.services.summarizer import generate_daily_summary

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        owner_ids = (
            await session.execute(
                select(TimelineEntry.owner_user_id)
                .where(
                    TimelineEntry.logical_date == today,
                    TimelineEntry.owner_user_id.is_not(None),
                )
                .distinct()
            )
        ).scalars().all()
        for owner_user_id in owner_ids:
            await generate_daily_summary(
                session,
                today,
                owner_user_id=owner_user_id,
            )
        logger.info("Daily summaries generated for %s (%d owners)", today, len(owner_ids))


async def _run_scheduled_embeddings():
    """Enrich lexical recall documents without blocking ingestion."""
    async with async_session_factory() as session:
        from app.services.retrieval import embed_pending_documents

        count = await embed_pending_documents(session, limit=100)
        await session.commit()
        if count:
            logger.info("Generated embeddings for %d recall documents", count)


async def _run_upload_cleanup():
    """Expire abandoned resumable uploads and reclaim temporary storage."""
    async with async_session_factory() as session:
        from app.services.uploads import expire_upload_sessions

        count = await expire_upload_sessions(session)
        if count:
            logger.info("Expired %d abandoned upload sessions", count)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting LifeLog server...")

    await init_db()
    logger.info("Database initialized")

    async with async_session_factory() as session:
        from app.core.extension_utils import sync_extensions_db
        from app.services.prompts import seed_default_prompts
        await sync_extensions_db(session)
        await seed_default_prompts(session)
    logger.info("Default prompts seeded")

    arq_pool = None
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        arq_pool = await create_pool(
            RedisSettings.from_dsn(settings.REDIS_URL),
            retry=0,
        )
        app.state.arq_pool = arq_pool
        logger.info("Connected to Redis")
    except Exception:
        logger.exception("Redis unavailable — background workers disabled")

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
        scheduler.add_job(
            _run_scheduled_timeline,
            "interval",
            minutes=settings.SESSIONIZER_INTERVAL_MINUTES,
            id="timeline",
            replace_existing=True,
        )
        scheduler.add_job(
            _run_scheduled_summary,
            "cron",
            hour=settings.SUMMARY_CRON_HOUR,
            minute=settings.SUMMARY_CRON_MINUTE,
            id="daily_summary",
            replace_existing=True,
        )
        scheduler.add_job(
            _run_scheduled_embeddings,
            "interval",
            minutes=5,
            id="retrieval_embeddings",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            _run_upload_cleanup,
            "interval",
            hours=1,
            id="upload_cleanup",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        from app.services.extension_runtime import configure_extension_pollers
        poller_count = await configure_extension_pollers(scheduler, arq_pool)
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info(
            "Scheduler started (sessionizer every %d min)",
            settings.SESSIONIZER_INTERVAL_MINUTES,
        )
        logger.info("Configured %d extension pollers", poller_count)
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
app.include_router(inbox.router, prefix="/api/v1", tags=["inbox"])
app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(devices.router, prefix="/api/v1", tags=["devices"])
app.include_router(ingest.router, prefix="/api/v1", tags=["ingestion"])
app.include_router(timeline.router, prefix="/api/v1", tags=["timeline"])
app.include_router(summaries.router, prefix="/api/v1", tags=["summaries"])
app.include_router(admin.router, prefix="/api/v1", tags=["admin"])
app.include_router(data.router, prefix="/api/v1", tags=["data"])
app.include_router(search.router, prefix="/api/v1/search", tags=["search"])
app.include_router(ai_chat.router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(extensions.router, prefix="/api/v1", tags=["extensions"])
app.include_router(files.router, prefix="/api/v1/files", tags=["files"])
app.include_router(client.router, prefix="/api/v1", tags=["client"])
app.include_router(commitments.router, prefix="/api/v1", tags=["commitments"])
app.include_router(kernel.router, prefix="/api/v1/kernel", tags=["kernel"])
app.include_router(life_areas.router, prefix="/api/v1", tags=["life-areas"])
app.include_router(captures.router, prefix="/api/v1", tags=["captures"])
app.include_router(sources.router, prefix="/api/v1", tags=["sources"])

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

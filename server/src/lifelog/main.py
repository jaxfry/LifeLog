from fastapi import FastAPI, APIRouter
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from .api import (
    ingestion,
    extensions,
    event_types,
    processing,
    auth,
    timeline,
    devices,
    actor_routing,
    search,
    synthesis,
    ai as ai_api,
    device as device_api,
)
from .actors import load_all_actors
from .db import init_db
from .core.config import settings
from .core.extension_loader import init_extension_loader, get_extension_loader

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")
    # Security hardening checks
    insecure_secret = settings.SECRET_KEY == "your-secret-key-change-in-production"
    insecure_admin_pw = settings.LIFELOG_PASSWORD == "admin123"
    has_pw_hash = getattr(settings, "LIFELOG_PASSWORD_HASH", None) is not None
    if settings.APP_ENV.lower() == "production":
        # In production, refuse to start with insecure defaults
        if insecure_secret:
            raise RuntimeError("SECURITY: SECRET_KEY must be set to a strong random value in production.")
        if not has_pw_hash:
            raise RuntimeError("SECURITY: LIFELOG_PASSWORD_HASH must be set (bcrypt) in production.")
    else:
        # In development, warn loudly
        if insecure_secret:
            logger.warning("Using default SECRET_KEY; set a strong value via env.")
        if insecure_admin_pw and not has_pw_hash:
            logger.warning("Using default admin password; set LIFELOG_PASSWORD or LIFELOG_PASSWORD_HASH.")

    # Ensure DB schema exists in development (no-op if already migrated)
    try:
        await init_db()
    except Exception as e:
        # Avoid blocking startup; schema might already be created via Alembic
        logger.warning("DB init skipped or failed: %s", e)
    
    # Load built-in actors (from actors/ directory)
    load_all_actors()
    
    # Initialize extension loader and load all dynamic extensions
    extensions_path = Path(settings.EXTENSIONS_PATH)
    ext_loader = init_extension_loader(extensions_path)
    loaded_extensions = await ext_loader.load_all_extensions()
    logger.info(f"Loaded {len(loaded_extensions)} dynamic extensions with auto-registration")
    
    logger.info("Application startup complete.")
    yield
    logger.info("Shutting down application.")
    
    # Clean up temporary extension files
    try:
        ext_loader = get_extension_loader()
        ext_loader.cleanup()
    except Exception as e:
        logger.error(f"Failed to clean up extension loader: {e}")

app = FastAPI(
    title="LifeLog API",
    description="The central server for the LifeLog system with versioned APIs.",
    version="1.0.0",
    lifespan=lifespan
)

# Create API v1 router for client-facing APIs
api_v1_router = APIRouter(prefix=settings.API_V1_STR)

# Client Data API - authenticated endpoints for client applications
api_v1_router.include_router(auth.router, tags=["Authentication"])
api_v1_router.include_router(timeline.router, tags=["Timeline"])
api_v1_router.include_router(search.router, tags=["Search"]) 
api_v1_router.include_router(device_api.router)

# Include the v1 router in the main app
app.include_router(api_v1_router)

# Internal Actor API - for internal system management (will add authentication later)
internal_router = APIRouter(prefix="/internal", tags=["Internal"])
internal_router.include_router(extensions.router)
internal_router.include_router(event_types.router)
internal_router.include_router(processing.router)
internal_router.include_router(devices.router)
internal_router.include_router(actor_routing.router)
internal_router.include_router(synthesis.router)
internal_router.include_router(ai_api.router)

app.include_router(internal_router)

# Ingestion API - separate from versioned APIs as per architecture
app.include_router(ingestion.router, tags=["Ingestion"])

@app.get("/")
def read_root():
    return {
        "status": "ok", 
        "message": "Welcome to the LifeLog API!",
        "version": "1.0.0",
        # FastAPI's docs live at /docs; keep link simple in development
        "docs": "/docs" if settings.APP_ENV == "development" else None
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "lifelog-api"}

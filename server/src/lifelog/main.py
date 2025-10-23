from fastapi import FastAPI, APIRouter
from contextlib import asynccontextmanager

from .api import ingestion, extensions, event_types, processing, auth, timeline, devices
from .actors import load_all_actors
from .db import init_db
from .core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("INFO:     Application starting up...")
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
            print("WARNING:    Using default SECRET_KEY; set a strong value via env.")
        if insecure_admin_pw and not has_pw_hash:
            print("WARNING:    Using default admin password; set LIFELOG_PASSWORD or LIFELOG_PASSWORD_HASH.")

    # Ensure DB schema exists in development (no-op if already migrated)
    try:
        await init_db()
    except Exception as e:
        # Avoid blocking startup; schema might already be created via Alembic
        print(f"WARNING:    DB init skipped or failed: {e}")
    load_all_actors()
    print("INFO:     Application startup complete.")
    yield
    print("INFO:     Shutting down application.")

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

# Include the v1 router in the main app
app.include_router(api_v1_router)

# Internal Actor API - for internal system management (will add authentication later)
internal_router = APIRouter(prefix="/internal", tags=["Internal"])
internal_router.include_router(extensions.router)
internal_router.include_router(event_types.router)
internal_router.include_router(processing.router)
internal_router.include_router(devices.router)

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

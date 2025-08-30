from fastapi import FastAPI, APIRouter
from contextlib import asynccontextmanager

from .api import ingestion, extensions, event_types, processing, auth, timeline
from .actors import load_all_actors
from .core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("INFO:     Application starting up...")
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

app.include_router(internal_router)

# Ingestion API - separate from versioned APIs as per architecture
app.include_router(ingestion.router, tags=["Ingestion"])

@app.get("/")
def read_root():
    return {
        "status": "ok", 
        "message": "Welcome to the LifeLog API!",
        "version": "1.0.0",
        "docs": f"{settings.API_V1_STR}/docs" if settings.APP_ENV == "development" else None
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "lifelog-api"}

import logging
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from central_server.api_service.core.database import init_db
from central_server.api_service.core.settings import settings
from central_server.api_service.api_v1.endpoints import auth, projects, timeline, events, day, system

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up LifeLog API Service...")
    try:
        await init_db()
        logger.info("Database initialized successfully.")
        logger.info(f"Using single-user authentication with username: {settings.LIFELOG_USERNAME}")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down LifeLog API Service...")

app = FastAPI(
    title="LifeLog API Service",
    description="Unified API service for the LifeLog application with authentication, data management, and analytics.",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create API v1 router
api_v1_router = APIRouter(prefix=settings.API_V1_STR)

# Include all endpoint routers
api_v1_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_v1_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_v1_router.include_router(timeline.router, prefix="/timeline", tags=["Timeline"])
api_v1_router.include_router(events.router, prefix="/events", tags=["Events"])
api_v1_router.include_router(day.router, prefix="/day", tags=["Daily Data"])
api_v1_router.include_router(system.router, prefix="/system", tags=["System"])

# Include the v1 router in the main app
app.include_router(api_v1_router)

# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to the LifeLog API Service",
        "version": "1.0.0",
        "docs": f"{settings.API_V1_STR}/docs"
    }

# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": "lifelog-api"}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server for development...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

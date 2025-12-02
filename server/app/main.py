from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from app.core.db import init_db
from app.core.scheduler import start_scheduler, stop_scheduler
from app.core.logger import setup_logging, get_logger
from app.api import ingest, data, admin, client, health, auth, analytics, ai_chat, extensions, search
from arq import create_pool
from arq.connections import RedisSettings
import os
from dotenv import load_dotenv
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.core.rate_limit import limiter

load_dotenv()

# Setup logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE = os.environ.get("LOG_FILE", None)
setup_logging(log_level=LOG_LEVEL, log_file=LOG_FILE)
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    
    # Initialize ARQ Redis Pool
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    app.state.arq_pool = await create_pool(RedisSettings.from_dsn(redis_url))
    
    start_scheduler()
    
    yield
    
    stop_scheduler()
    
    if hasattr(app.state, "arq_pool"):
        await app.state.arq_pool.close()

app = FastAPI(title="LifeLog Core", version="4.0", lifespan=lifespan)

# Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Security Middleware
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

# CORS Middleware
BACKEND_CORS_ORIGINS = os.environ.get("BACKEND_CORS_ORIGINS", "http://localhost:3000,http://localhost:8000,http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(ingest.router, prefix="/api/v1", tags=["ingestion"])
app.include_router(data.router, prefix="/api/v1", tags=["data"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(admin.router, prefix="/api/v1", tags=["admin"])
app.include_router(client.router, prefix="/api/v1", tags=["client"])
app.include_router(ai_chat.router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(extensions.router, prefix="/api/v1", tags=["extensions"])
app.include_router(search.router, prefix="/api/v1/search", tags=["search"])

@app.get("/")
async def root():
    return {"message": "LifeLog System Online", "version": "4.0"}

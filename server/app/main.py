from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.db import init_db
from app.core.scheduler import start_scheduler, stop_scheduler
from app.core.logger import setup_logging, get_logger
from app.api import ingest, data, admin, client
from arq import create_pool
from arq.connections import RedisSettings
import os
from dotenv import load_dotenv

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

app.include_router(ingest.router, prefix="/api/v1", tags=["ingestion"])
app.include_router(data.router, prefix="/api/v1", tags=["data"])
app.include_router(admin.router, prefix="/api/v1", tags=["admin"])
app.include_router(client.router, prefix="/api/v1", tags=["client"])

@app.get("/")
async def root():
    return {"message": "LifeLog System Online", "version": "4.0"}

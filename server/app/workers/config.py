import os

from app.core.logger import get_logger

logger = get_logger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
"""
ARQ WorkerSettings are defined here and can be imported by `arq` CLI or by the
lifespan startup in main.py.

Usage:
    arq app.workers.config.WorkerSettings

Or programmatically:
    from app.workers.config import create_worker
"""

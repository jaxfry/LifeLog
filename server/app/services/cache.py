import hashlib
import json
from datetime import timedelta
from typing import Any, Optional

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_redis = None


def _cache_key(prefix: str, data: dict[str, Any]) -> str:
    raw = json.dumps(data, sort_keys=True, default=str)
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"llm:{prefix}:{h}"


async def _get_redis():
    global _redis
    if _redis is None:
        try:
            import redis.asyncio as aioredis

            _redis = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
            await _redis.ping()
            logger.info("LLM cache connected to Redis")
        except Exception:
            _redis = False
            logger.warning("LLM cache disabled (Redis unavailable)")
    return _redis if _redis is not False else None


async def get_cached_response(cache_key: str) -> Optional[str]:
    r = await _get_redis()
    if r is None:
        return None
    try:
        val = await r.get(cache_key)
        return val.decode() if val else None
    except Exception:
        return None


async def set_cached_response(cache_key: str, response: str) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.setex(cache_key, timedelta(hours=settings.LLM_CACHE_TTL_HOURS), response)
    except Exception:
        pass


async def invalidate_cache(pattern: str = "*") -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        keys = await r.keys(f"llm:{pattern}")
        if keys:
            await r.delete(*keys)
    except Exception:
        pass

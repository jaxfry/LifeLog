import os

from redis import Redis

from app.core.logger import get_logger

logger = get_logger(__name__)

class ProcessingLock:
    """
    Distributed lock to prevent concurrent reprocessing operations.
    Uses Redis with auto-expiration for crash recovery.
    """

    def __init__(self, redis_url: str | None = None):
        if redis_url is None:
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

        # Parse redis URL for Redis connection
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.lock_key = "lifelog:reprocessing:lock"
        self.progress_key = "lifelog:reprocessing:progress"
        self.lock_timeout = 3600  # 1 hour - auto-expire if process crashes

    def acquire(self, job_id: str) -> bool:
        """
        Attempts to acquire the lock.
        Returns True if lock acquired, False if another job is running.
        """
        try:
            # Try to set lock with NX (only if not exists) and EX (expiration)
            result = self.redis.set(
                self.lock_key,
                job_id,
                nx=True,
                ex=self.lock_timeout
            )

            if result:
                logger.info(f"Lock acquired for job {job_id}")
                return True
            else:
                current_owner = self.redis.get(self.lock_key)
                logger.warning(f"Lock already held by {current_owner}")
                return False

        except Exception as e:
            logger.error(f"Error acquiring lock: {e}")
            return False

    def release(self, job_id: str):
        """
        Releases the lock if owned by this job_id.
        """
        try:
            current_owner = self.redis.get(self.lock_key)
            if current_owner == job_id:
                self.redis.delete(self.lock_key)
                self.redis.delete(self.progress_key)
                logger.info(f"Lock released for job {job_id}")
            else:
                logger.warning(f"Cannot release lock - owned by {current_owner}, not {job_id}")
        except Exception as e:
            logger.error(f"Error releasing lock: {e}")

    def is_locked(self) -> bool:
        """Check if lock is currently held."""
        return self.redis.exists(self.lock_key) > 0

    def get_current_job(self) -> str | None:
        """Get the job ID that currently holds the lock."""
        return self.redis.get(self.lock_key)

    def update_progress(self, progress_data: dict):
        """Update progress information for monitoring."""
        try:
            self.redis.hset(self.progress_key, mapping=progress_data)
            # Auto-expire progress with the lock
            self.redis.expire(self.progress_key, self.lock_timeout)
        except Exception as e:
            logger.error(f"Error updating progress: {e}")

    def get_progress(self) -> dict | None:
        """Get current progress information."""
        try:
            if self.redis.exists(self.progress_key):
                return self.redis.hgetall(self.progress_key)
            return None
        except Exception as e:
            logger.error(f"Error getting progress: {e}")
            return None

    def extend_lock(self, job_id: str):
        """Extend lock expiration for long-running jobs."""
        try:
            current_owner = self.redis.get(self.lock_key)
            if current_owner == job_id:
                self.redis.expire(self.lock_key, self.lock_timeout)
                logger.debug(f"Extended lock for job {job_id}")
        except Exception as e:
            logger.error(f"Error extending lock: {e}")

# Global instance
_lock = None

def get_processing_lock() -> ProcessingLock:
    """Get or create the global processing lock instance."""
    global _lock
    if _lock is None:
        _lock = ProcessingLock()
    return _lock

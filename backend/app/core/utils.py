import time
import logging
import random
from functools import wraps

log = logging.getLogger(__name__)

def with_db_write_retry(max_retries: int = 5, initial_delay_seconds: float = 0.5, backoff_factor: float = 2.0):
    """
    A decorator to retry a function call with exponential backoff and jitter
    if a database write lock occurs (Postgres version).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            delay = initial_delay_seconds
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    # Check if the error is specifically a lock error (Postgres style)
                    pgcode = getattr(e, 'pgcode', None)
                    if pgcode == '55P03':  # 55P03: lock_not_available
                        retries += 1
                        if retries >= max_retries:
                            log.error(f"DB write lock error: Max retries ({max_retries}) reached for {func.__name__}. Aborting.")
                            raise

                        # Exponential backoff with jitter
                        jitter = random.uniform(0, delay * 0.25)  # Add up to 25% jitter
                        sleep_time = delay + jitter

                        log.warning(
                            f"DB write lock on {func.__name__}. Retrying in {sleep_time:.2f}s... "
                            f"(Attempt {retries}/{max_retries})"
                        )
                        time.sleep(sleep_time)

                        # Increase delay for next retry
                        delay *= backoff_factor
                    else:
                        # Re-raise if it's a different, unexpected error
                        raise
        return wrapper
    return decorator

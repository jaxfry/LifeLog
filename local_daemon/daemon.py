"""
Local Daemon for LifeLog.
Continuously collects user activity, caches it locally, and sends it to a central server.
"""
import logging
import time
import sys
import os
from typing import Optional
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Handle imports for both package and direct script execution
# Add the parent directory to path so we can import local_daemon as a package
if __name__ == "__main__":
    # When running as a script, add parent directory to path
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    # Import as package
    from local_daemon import config
    from local_daemon import cache
    from local_daemon.collector import ActivityWatchCollector
    from local_daemon.sender import attempt_send_cached_data
else:
    # When imported as module
    from . import config
    from . import cache
    from .collector import ActivityWatchCollector
    from .sender import attempt_send_cached_data


# ---------------------------------------------------------------------------
# LOGGING SETUP
# ---------------------------------------------------------------------------
def setup_logging():
    """Configures logging for the daemon."""
    log_format = "%(asctime)s - %(levelname)s - [%(threadName)s:%(name)s] - %(message)s"
    log_level = getattr(logging, config.LOG_LEVEL, logging.INFO)
    
    # Create a base logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level) # Set level on root logger

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    # File Handler (optional)
    if config.LOG_FILE:
        try:
            file_handler = logging.FileHandler(config.LOG_FILE, mode='a') # Append mode
            file_handler.setFormatter(logging.Formatter(log_format))
            root_logger.addHandler(file_handler)
            print(f"Logging to file: {config.LOG_FILE}")
        except Exception as e:
            print(f"Error setting up file logger at {config.LOG_FILE}: {e}", file=sys.stderr)
            # Continue without file logging if it fails

    # Set specific log levels for noisy libraries if needed
    logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO) # Can be noisy
    logging.getLogger("aw_client.client").setLevel(logging.INFO) # Can be noisy

    # Get the logger for this module
    return logging.getLogger(__name__)

log = setup_logging()

# ---------------------------------------------------------------------------
# GLOBAL DAEMON COMPONENTS
# ---------------------------------------------------------------------------
scheduler: Optional[BackgroundScheduler] = None
aw_collector: Optional[ActivityWatchCollector] = None

# ---------------------------------------------------------------------------
# JOB DEFINITIONS
# ---------------------------------------------------------------------------

def collection_job():
    """Scheduled job to collect data using ActivityWatchCollector."""
    if aw_collector:
        log.info("Running scheduled data collection job...")
        try:
            aw_collector.collect_and_store_events()
            log.info(f"Collection job finished. Current cache size: {cache.get_cache_size()}")
        except Exception as e:
            log.error(f"Error during scheduled data collection: {e}", exc_info=True)
    else:
        log.warning("ActivityWatchCollector not initialized. Skipping collection job.")

def sending_job():
    """Scheduled job to attempt sending cached data to the server."""
    log.info("Running scheduled data sending job...")
    try:
        attempt_send_cached_data()
        log.info(f"Sending job finished. Current cache size: {cache.get_cache_size()}")
    except Exception as e:
        log.error(f"Error during scheduled data sending: {e}", exc_info=True)

# ---------------------------------------------------------------------------
# MAIN DAEMON LIFECYCLE
# ---------------------------------------------------------------------------

def start_daemon():
    global scheduler, aw_collector
    log.info("--- Starting LifeLog Local Daemon ---")

    # Initialize components
    try:
        cache.initialize_cache() # Ensure cache is ready
        aw_collector = ActivityWatchCollector()
        if not aw_collector.aw_client: # Check if AW client failed to init
             log.error("ActivityWatch client could not be initialized. Data collection might fail.")
             # Decide if daemon should exit or continue without AW collection
             # For now, it will continue but log warnings.
    except Exception as e:
        log.error(f"Fatal error during daemon initialization: {e}", exc_info=True)
        # Depending on severity, might sys.exit(1) here
        return False # Indicate startup failure

    # Initialize and configure scheduler
    scheduler = BackgroundScheduler(timezone="UTC") # Use UTC for scheduler internal logic

    # Add collection job
    scheduler.add_job(
        collection_job,
        trigger=IntervalTrigger(seconds=config.COLLECTION_INTERVAL_SECONDS),
        id="data_collection_job",
        name="Data Collector",
        max_instances=1,
        coalesce=True, # If multiple runs are due, only run the latest one
        misfire_grace_time=30 # Grace time in seconds if scheduler was asleep
    )
    log.info(f"Scheduled data collection job to run every {config.COLLECTION_INTERVAL_SECONDS} seconds.")

    # Add sending job
    scheduler.add_job(
        sending_job,
        trigger=IntervalTrigger(seconds=config.BATCH_SEND_INTERVAL_SECONDS),
        id="data_sending_job",
        name="Data Sender",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60
    )
    log.info(f"Scheduled data sending job to run every {config.BATCH_SEND_INTERVAL_SECONDS} seconds.")

    # Start the scheduler
    try:
        scheduler.start()
        log.info("Scheduler started. Daemon is now running.")
        
        # Optionally, run an initial collection and send attempt on startup
        log.info("Performing initial data collection and send attempt on startup...")
        collection_job() # Initial collection
        sending_job()    # Initial send attempt
        log.info("Initial tasks complete.")

        return True # Indicate successful startup
    except Exception as e:
        log.error(f"Failed to start scheduler: {e}", exc_info=True)
        return False

def stop_daemon():
    global scheduler
    log.info("--- Stopping LifeLog Local Daemon ---")
    if scheduler and scheduler.running:
        try:
            scheduler.shutdown(wait=True) # Wait for jobs to complete
            log.info("Scheduler shut down gracefully.")
        except Exception as e:
            log.error(f"Error shutting down scheduler: {e}", exc_info=True)
            # Force shutdown if graceful fails
            try:
                scheduler.shutdown(wait=False)
                log.info("Scheduler shut down forcefully.")
            except Exception as e2:
                log.error(f"Error during forceful scheduler shutdown: {e2}", exc_info=True)

    else:
        log.info("Scheduler was not running or not initialized.")
    log.info("LifeLog Local Daemon stopped.")

def main():
    if start_daemon():
        try:
            # Keep the main thread alive while the scheduler runs in the background
            while True:
                time.sleep(1) # Sleep for a short duration, can be longer
        except (KeyboardInterrupt, SystemExit):
            log.info("Shutdown signal received.")
        finally:
            stop_daemon()
    else:
        log.error("Daemon failed to start. Exiting.")
        sys.exit(1)

if __name__ == "__main__":
    # This allows running the daemon directly.
    # Ensure that the current working directory or PYTHONPATH allows finding submodules.
    # If running from /Users/jaxon/Coding/LifeLog, and local_daemon is a subdirectory,
    # you might need to run as `python -m local_daemon.daemon` for imports to work correctly
    # without the sys.path modification in the try-except block at the top.
    # The try-except ImportError block is a workaround for direct script execution.
    main()
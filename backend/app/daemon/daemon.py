import logging
import time
import threading
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.app.core.settings import settings
from backend.app.core.runner import run_transactional_job
from backend.app.core.db import backup_database, get_meta, set_meta
from backend.app.ingestion.activitywatch import ingest_aw_window
from backend.app.processing.timeline import process_pending_events_sync
from backend.app.daemon.realtime_watcher import main as realtime_watcher_main
from aw_client import ActivityWatchClient # Added for health check

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(threadName)s:%(name)s] - %(message)s",
)
log = logging.getLogger("lifelog.batch_daemon")

# ---------------------------------------------------------------------------
# GLOBALS
# ---------------------------------------------------------------------------

# Prevent overlapping daily batches (APScheduler is configured for 1 instance
# but the lock keeps us safe if you ever call the job manually).
_batch_lock = threading.Lock()
_realtime_watcher_thread = None
# watcher_alive = threading.Event() # Replaced by watcher_status
watcher_status = {
    'alive_event': threading.Event(),
    'last_event_ts': None,
    'lock': threading.Lock()
}

# ---------------------------------------------------------------------------
# JOB DEFINITIONS
# ---------------------------------------------------------------------------


def reconciliation_ingestor_job(con):
    """Catch‑up job that ingests ActivityWatch data since the last run."""
    last_ts_str = get_meta(con, 'last_aw_ts')
    if last_ts_str:
        last_ts = datetime.fromisoformat(last_ts_str)
    else:
        # If no last_ts, go back 1 day as a default starting point
        last_ts = datetime.now(timezone.utc) - timedelta(days=1)

    # Small overlap for idempotency and to catch events that might have been
    # written slightly after the previous run's end_utc.
    start_utc = last_ts - timedelta(hours=2)
    end_utc = datetime.now(timezone.utc)

    log.info(
        "Running reconciliation ingestion job (last_aw_ts: %s) [%s → %s]...",
        last_ts_str or "N/A",
        start_utc.isoformat(),
        end_utc.isoformat()
    )
    ingest_aw_window(con, settings, start_utc, end_utc)
    set_meta(con, 'last_aw_ts', end_utc.isoformat())


def batch_processor_job(con):
    """One‑shot daily processor that turns staged events into timeline entries."""
    if not _batch_lock.acquire(blocking=False):
        log.warning("Batch processor already running; skipping this run.")
        return
    try:
        log.info("Running batch timeline processing job...")
        process_pending_events_sync(con, settings)
    finally:
        _batch_lock.release()


def backup_job(con):
    log.info("Running backup job…")
    backup_database()


SERVICE_UNAVAILABLE_MESSAGE = "AW server health check failed: service unavailable or network issue."

def aw_server_health_check_job(): # Removed db_connection, not used for now
    """Periodically checks the ActivityWatch server health."""
    log.info("Running ActivityWatch server health check...")
    aw_client = ActivityWatchClient(client_name="lifelog_daemon_aw_health_check", testing=False)
    # Using a common endpoint, usually /api/0/info or similar
    # aw_client.get_info() is a good candidate if it exists and is lightweight.
    # For now, let's assume get_info() is the correct method.
    # If not, a raw request to /api/0/info would be needed.
    try:
        info = aw_client.get_info() # This is a method in newer aw-client versions
        if info and isinstance(info, dict) and "version" in info: # Check for a valid response structure
            log.info(f"ActivityWatch server is healthy. Version: {info.get('version', 'N/A')}")
            # Optionally, set_meta(con, 'aw_server_last_healthy_ping', datetime.now(timezone.utc).isoformat())
        else:
            log.warning(f"ActivityWatch server health check returned unexpected or incomplete data: {info}")
            # Optionally, set_meta(con, 'aw_server_status', 'degraded_response')
    except ConnectionRefusedError:
        log.error(f"{SERVICE_UNAVAILABLE_MESSAGE} Connection refused.")
    except Exception as e: # Catch other potential exceptions like requests.exceptions.ConnectionError
        log.error(f"ActivityWatch server health check failed: {e}", exc_info=True)
        # Optionally, set_meta(con, 'aw_server_status', 'unhealthy')


# Placeholder for restarting the watcher thread
# In a real scenario, this would involve more robust thread management,
# potentially re-initializing resources or signaling the old thread to stop.
def restart_watcher():
    """Restarts the real-time watcher thread."""
    global _realtime_watcher_thread
    log.info("Attempting to restart real-time watcher...")

    # Basic restart: create and start a new thread.
    # Considerations for a robust implementation:
    # 1. Ensure the old thread is properly terminated (e.g., using a stop event).
    # 2. Handle potential errors during thread creation or start.
    # 3. Re-initialize any necessary resources for the watcher.
    # 4. Prevent multiple rapid restarts (e.g., with a backoff).

    if _realtime_watcher_thread and _realtime_watcher_thread.is_alive():
        log.warning("Real-time watcher thread is still alive. Not restarting yet.")
        # Optionally, implement a more forceful stop or wait mechanism here.
        # For now, we'll rely on the watchdog's timeout to try again later
        # if the watcher is truly stuck and not just slow to respond.
        return

    # Clear status before restart to avoid using stale data from a previous run immediately
    with watcher_status['lock']:
        watcher_status['last_event_ts'] = None
    watcher_status['alive_event'].clear()


    _realtime_watcher_thread = threading.Thread(
        target=realtime_watcher_main,
        args=[watcher_status], # Pass the shared status object
        name="RealtimeWatcher",
        daemon=True
    )
    _realtime_watcher_thread.start()
    log.info("New real-time watcher thread started.")


def watchdog():
    """Monitors the real-time watcher and restarts it if it stalls."""
    log.info("Real-time watcher watchdog started.")
    # Use the configured threshold from settings
    threshold_minutes = settings.WATCHER_TIMESTAMP_THRESHOLD_MINUTES

    while True:
        # Wait for the watcher to signal it's alive via the event.
        # Timeout after 120 seconds (2 minutes) - this remains the primary liveness check.
        if not watcher_status['alive_event'].wait(timeout=120):
            log.error("Real-time watcher heartbeat (event) NOT received within timeout. Restarting watcher...")
            restart_watcher()
        else:
            # Event was set, watcher is responsive. Now check timestamp freshness.
            with watcher_status['lock']:
                last_ts = watcher_status['last_event_ts']
            
            if last_ts:
                # Ensure last_ts is timezone-aware if it's coming from realtime_watcher
                # datetime.now(timezone.utc) is timezone-aware.
                if not last_ts.tzinfo:
                    log.warning("Watcher's last_event_ts is naive, assuming UTC for comparison.")
                    last_ts = last_ts.replace(tzinfo=timezone.utc)

                if datetime.now(timezone.utc) - last_ts > timedelta(minutes=threshold_minutes):
                    log.error(
                        f"Real-time watcher's last event/poll timestamp ({last_ts.isoformat()}) is older than "
                        f"{threshold_minutes} minutes. Restarting watcher..."
                    )
                    restart_watcher()
                else:
                    log.debug(f"Real-time watcher heartbeat received. Last event/poll timestamp {last_ts.isoformat()} is recent.")
            else:
                # This might happen on initial startup before the watcher has processed any event or polled.
                # It's not necessarily an error yet, but worth noting.
                log.info("Real-time watcher's last event/poll timestamp not yet available from watcher_status.")
            
        # Clear the event for the next cycle.
        # The watcher needs to set it again in its next successful loop iteration.
        watcher_status['alive_event'].clear()
        
        # Add a small sleep to prevent extremely tight looping if clear() and wait() cycle too fast,
        # though watcher_alive.wait(timeout=120) usually dictates the loop pace.
        # A short sleep here ensures the loop doesn't spin if wait() returns immediately.
        time.sleep(5) # Reduced from 1 to 5 to give more breathing room, but main delay is wait()


# ---------------------------------------------------------------------------
# MAIN DAEMON ENTRYPOINT
# ---------------------------------------------------------------------------


def main() -> None:
    log.info("--- Starting LifeLog Batch Daemon (APScheduler edition) ---")

    # APScheduler handles its own thread pool and respects time‑zones.
    scheduler = BackgroundScheduler(timezone=settings.LOCAL_TZ)

    # Reconciliation every 4 hours (cheap, no LLM).
    scheduler.add_job(
        run_transactional_job,
        trigger=IntervalTrigger(hours=4),
        args=[reconciliation_ingestor_job],
        id="reconciliation_ingestion",
        max_instances=1,
        misfire_grace_time=600,  # 10‑minute grace if the host was asleep
        coalesce=True,
    )

    # Daily batch (expensive) at 03:00 local time.
    scheduler.add_job(
        run_transactional_job,
        trigger=CronTrigger(hour=3, minute=0, timezone=settings.LOCAL_TZ),
        args=[batch_processor_job],
        id="batch_enrichment",     # Changed ID for clarity as per suggestion
        max_instances=1,  # Guard against overlaps
        misfire_grace_time=3600,  # 1‑hour grace window
        coalesce=True,
    )

    # Database backup 30 minutes after the batch.
    scheduler.add_job(
        run_transactional_job,
        trigger=CronTrigger(hour=3, minute=30, timezone=settings.LOCAL_TZ),
        args=[backup_job],
        id="database_backup",
        max_instances=1,
        misfire_grace_time=3600,
        coalesce=True,
    )

    # AW Server Health Check Job
    scheduler.add_job(
        aw_server_health_check_job, # Direct call, no DB ops in this version
        trigger=IntervalTrigger(minutes=settings.AW_HEALTH_CHECK_INTERVAL_MINUTES),
        id="aw_server_health_check",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,  # 5-minute grace
    )

    scheduler.start()
    log.info("Scheduler initialised with %d job(s)", len(scheduler.get_jobs()))

    # Immediate reconciliation to stage recent events.
    run_transactional_job(reconciliation_ingestor_job)

    # Real‑time watcher runs in its own daemon thread.
    log.info("Starting real‑time event watcher…")
    global _realtime_watcher_thread
    _realtime_watcher_thread = threading.Thread(
        target=realtime_watcher_main,
        args=[watcher_status], # Pass the shared status object
        name="RealtimeWatcher",
        daemon=True
    )
    _realtime_watcher_thread.start()

    # Start the watchdog thread for the real-time watcher
    watchdog_thread = threading.Thread(target=watchdog, name="WatcherWatchdog", daemon=True)
    watchdog_thread.start()

    log.info("Startup complete. Daemon is now running.")
    try:
        # Keep the main thread alive; APScheduler does the work.
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down scheduler…")
        scheduler.shutdown()
        log.info("LifeLog Batch Daemon stopped.")


if __name__ == "__main__":
    main()

import logging
import schedule
import time
import threading
from datetime import datetime, timedelta, timezone

from backend.app.core.settings import settings
from backend.app.core.runner import run_transactional_job
from backend.app.core.db import backup_database
from backend.app.ingestion.activitywatch import ingest_aw_window
from backend.app.processing.timeline import process_pending_events_sync
from backend.app.daemon.realtime_watcher import main as realtime_watcher_main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
)
log = logging.getLogger(__name__)

# --- JOB DEFINITIONS ---
# reconciliation_ingestor_job, batch_processor_job, backup_job are unchanged

def reconciliation_ingestor_job(con):
    """Safety net job to catch any events missed by the real-time watcher."""
    log.info("Running reconciliation ingestion job...")
    end_utc = datetime.now(timezone.utc)
    start_utc = end_utc - timedelta(hours=6) # 6 hours is a good safety margin
    ingest_aw_window(con, settings, start_utc, end_utc)

def batch_processor_job(con):
    """Processes all pending events into timeline entries. Now runs less frequently."""
    log.info("Running batch timeline processing job...")
    process_pending_events_sync(con, settings)

def backup_job(con):
    backup_database()

# --- MAIN DAEMON ---
def main():
    log.info("--- Starting LifeLog Batch Daemon (Optimized for API Usage) ---")

    # --- Schedule Jobs ---

    # RECONCILIATION: Still useful to run periodically to fill data gaps. No LLM cost.
    schedule.every(4).hours.do(run_transactional_job, reconciliation_ingestor_job)
    
    # BATCH PROCESSING (THE EXPENSIVE ONE): Run once per day.
    # This will process all events from the previous day in one large, efficient request.
    schedule.every().day.at("03:00", settings.LOCAL_TZ).do(run_transactional_job, batch_processor_job)
    
    # BACKUP: Remains the same.
    schedule.every().day.at("03:30", settings.LOCAL_TZ).do(run_transactional_job, backup_job)
    
    log.info("Jobs scheduled. Running initial reconciliation job on startup...")
    
    # Run reconciliation on startup to ensure recent data is staged.
    # We DO NOT run the batch processor on startup anymore to save API calls.
    run_transactional_job(reconciliation_ingestor_job)

    log.info("Starting real-time event watcher in a background thread...")
    watcher_thread = threading.Thread(target=realtime_watcher_main, name="RealtimeWatcher", daemon=True)
    watcher_thread.start()

    log.info("Startup job complete. Entering main loop.")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
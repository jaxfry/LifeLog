import logging
import schedule
import time
from datetime import datetime, timedelta, timezone

from backend.app.core.settings import settings
from backend.app.core.runner import run_transactional_job
from backend.app.core.db import backup_database
from backend.app.ingestion.activitywatch import ingest_aw_window
from backend.app.processing.timeline import process_pending_events

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
)
log = logging.getLogger(__name__)


# --- JOB DEFINITIONS ---
# These are thin wrappers that pass the correct arguments to the core logic.
# The runner passes the connection as the first parameter.

def live_ingestor_job(con):
    end_utc = datetime.now(timezone.utc)
    start_utc = end_utc - timedelta(minutes=10) # Look back 10 mins for live data
    ingest_aw_window(con, settings, start_utc, end_utc)

def reconciliation_ingestor_job(con):
    end_utc = datetime.now(timezone.utc)
    start_utc = end_utc - timedelta(hours=48) # Look back 2 days for reconciliation
    ingest_aw_window(con, settings, start_utc, end_utc)

def batch_processor_job(con):
    process_pending_events(con, settings)

def backup_job(con):
    # backup_database doesn't need the connection - it creates its own
    backup_database()

# --- MAIN DAEMON ---
def main():
    log.info("--- Starting LifeLog Daemon ---")

    # --- Schedule Jobs ---
    schedule.every(5).minutes.do(run_transactional_job, live_ingestor_job)
    schedule.every(2).hours.do(run_transactional_job, reconciliation_ingestor_job)
    schedule.every(1).hour.do(run_transactional_job, batch_processor_job)
    schedule.every().day.at("03:00", settings.LOCAL_TZ).do(run_transactional_job, backup_job)
    
    log.info("Jobs scheduled. Running initial jobs on startup...")
    
    # --- Run once on startup for immediate feedback ---
    run_transactional_job(reconciliation_ingestor_job)
    run_transactional_job(batch_processor_job)

    log.info("Startup jobs complete. Entering main loop.")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
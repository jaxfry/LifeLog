#!/usr/bin/env python3
"""
Standalone script to process events for a specific day by directly invoking the batch processor.
This script does NOT use RabbitMQ; it runs the same logic as the scheduled 3:00 AM job, but on demand.
"""

import logging
import sys
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# --- Import batch processor ---
try:
    from central_server.processing_service.batch_processor import run_batch_processing
    from central_server.processing_service.logic.settings import settings as service_settings
except ImportError:
    from ..central_server.processing_service.batch_processor import run_batch_processing
    from ..central_server.processing_service.logic.settings import settings as service_settings


def process_day(target_date_str: str):
    """
    Parses the date string and runs batch processing for that day.
    """
    log.info(f"--- Running batch processing for specific day: {target_date_str} ---")
    try:
        target_day = date.fromisoformat(target_date_str)
    except ValueError:
        log.error(f"Invalid date format: {target_date_str}. Please use YYYY-MM-DD.")
        return

    run_batch_processing(target_day)
    log.info(f"--- Batch processing for {target_date_str} finished ---")


if __name__ == "__main__":
    """
    Main entry point for the script.
    Accepts a date from the command line or prompts the user.
    Defaults to yesterday based on the configured timezone.
    """
    if len(sys.argv) > 1:
        date_to_process = sys.argv[1]
    else:
        # Default to yesterday based on the configured timezone
        try:
            local_tz = ZoneInfo(service_settings.LOCAL_TZ)
        except Exception:
            log.error(f"Invalid timezone '{getattr(service_settings, 'LOCAL_TZ', 'UTC')}' in settings. Falling back to UTC.")
            local_tz = ZoneInfo("UTC")
        yesterday = (datetime.now(local_tz) - timedelta(days=1)).strftime("%Y-%m-%d")
        date_to_process = input(f"Enter date to process (YYYY-MM-DD) [default: {yesterday}]: ") or yesterday
        if date_to_process == yesterday:
            log.info(f"No date provided. Using default (yesterday): {date_to_process}")

    process_day(date_to_process)
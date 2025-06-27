#!/usr/bin/env python3
"""
Standalone script to run ingestion and processing for a specific day on demand.

This script performs three main actions:
1.  Collects all events for a specified day from the local ActivityWatch instance.
2.  Sends these events to the central server's ingestion service via RabbitMQ.
3.  Sends a message to a dedicated RabbitMQ queue to trigger the batch processing 
    logic for that same day, bypassing the regular 3:00 AM schedule. 
    This is useful for reprocessing historical data or getting immediate results for a recent day.
"""

import os
import sys
import logging
from datetime import datetime, date, timedelta
import time
import json
import pika
from pika.exceptions import AMQPConnectionError
from zoneinfo import ZoneInfo

# Add project root to sys.path to allow for sibling imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# Import local daemon collector and sender
from local_daemon.collector import ActivityWatchCollector
from local_daemon.sender import send_data_to_server
# Import settings to get the timezone and RabbitMQ config
from central_server.processing_service.logic.settings import settings as service_settings
from central_server.processing_service.worker import (
    RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASS, PROCESSING_QUEUE
)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)


def collect_events_for_day(collector, target_date: date):
    """
    Collects all ActivityWatch events for the specified day.
    """
    local_tz = ZoneInfo(service_settings.LOCAL_TZ)

    start_of_day_local = datetime.combine(target_date, datetime.min.time(), tzinfo=local_tz)
    end_of_day_local = datetime.combine(target_date, datetime.max.time(), tzinfo=local_tz)

    # Convert to UTC for querying ActivityWatch
    start_utc = start_of_day_local.astimezone(ZoneInfo("UTC"))
    end_utc = end_of_day_local.astimezone(ZoneInfo("UTC"))

    log.info(f"Collecting events for {target_date} from {start_utc} to {end_utc}")

    events = collector.collect_all_events(start_utc, end_utc)
    log.info(f"Collected {len(events)} events from ActivityWatch.")
    return events


def trigger_processing_via_rabbitmq(target_date: date):
    """
    Sends a message to the processing queue to trigger batch processing.
    """
    log.info(f"--- Step 3: Triggering batch processing for {target_date} via RabbitMQ ---")
    
    connection = None
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        connection = pika.BlockingConnection(pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            credentials=credentials
        ))
        channel = connection.channel()
        
        channel.queue_declare(queue=PROCESSING_QUEUE, durable=True)
        
        message_body = json.dumps({'target_date': target_date.isoformat()})
        
        channel.basic_publish(
            exchange='',
            routing_key=PROCESSING_QUEUE,
            body=message_body,
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            ))
        log.info(f"Successfully sent processing request for {target_date} to queue '{PROCESSING_QUEUE}'")
        return True
    except AMQPConnectionError as e:
        log.error(f"Failed to connect to RabbitMQ: {e}")
        return False
    except Exception as e:
        log.error(f"An unexpected error occurred while sending to RabbitMQ: {e}")
        return False
    finally:
        if connection and connection.is_open:
            connection.close()


def main(target_date_str: str):
    """
    Main function to collect, send, and trigger processing for a specific day.
    """
    log.info(f"--- Starting on-demand ingestion and processing for: {target_date_str} ---")
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError:
        log.error("Invalid date format. Please use YYYY-MM-DD.")
        return

    # 1. Collect data from ActivityWatch
    log.info("--- Step 1: Collecting events from ActivityWatch ---")
    collector = ActivityWatchCollector()
    events = collect_events_for_day(collector, target_date)

    if not events:
        log.warning("No events collected. Skipping ingestion and processing.")
        return

    # 2. Send collected data to the server's ingestion queue
    log.info(f"--- Step 2: Sending {len(events)} events to the ingestion service ---")
    if not send_data_to_server(events):
        log.error("Failed to send data to server. Aborting processing.")
        return
    log.info("Data successfully sent to server for ingestion.")

    # Give a moment for the events to be ingested and stored by the worker.
    log.info("Waiting for 5 seconds for events to be ingested by the worker...")
    time.sleep(5)

    # 3. Trigger batch processing via RabbitMQ
    if not trigger_processing_via_rabbitmq(target_date):
        log.error("Failed to trigger processing. Please check RabbitMQ connection and worker status.")
        return

    log.info(f"--- On-demand script for {target_date_str} finished ---")


if __name__ == "__main__":
    """
    Main entry point for the script.
    Accepts a date from the command line or prompts the user.
    Defaults to yesterday.
    """
    if len(sys.argv) > 1:
        date_to_process = sys.argv[1]
    else:
        # Default to yesterday in the service's configured timezone
        local_tz = ZoneInfo(service_settings.LOCAL_TZ)
        yesterday = datetime.now(local_tz).date() - timedelta(days=1)
        date_to_process = yesterday.strftime("%Y-%m-%d")
        log.info(f"No date provided. Defaulting to yesterday ({service_settings.LOCAL_TZ}): {date_to_process}")

    main(date_to_process)

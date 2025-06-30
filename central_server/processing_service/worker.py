from datetime import timedelta, datetime, timezone
from typing import List
from pika.exceptions import AMQPConnectionError
from pydantic import ValidationError
from sqlalchemy.orm import Session as SQLAlchemySession
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
import os
import json
import uuid
import hashlib
import logging
import time
import pika

# Add project root to sys.path to allow for sibling imports
import sys
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# --- Pydantic Model Imports ---
from central_server.processing_service.models import InputLogPayload, ProcessingRequestPayload
from central_server.processing_service.batch_processor import run_batch_processing

# --- Database Imports ---
from central_server.processing_service.db_session import get_db_session, check_db_connection
from central_server.processing_service.db_models import (
    Event as EventOrm, DigitalActivityData, EventKind, TimelineEntryOrm,
    Project as ProjectOrm
)

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- RabbitMQ Configuration ---
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", 'localhost')
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
INGESTION_QUEUE = os.getenv("RABBITMQ_INGESTION_QUEUE", 'lifelog_events_queue')
PROCESSING_QUEUE = os.getenv("RABBITMQ_PROCESSING_QUEUE", 'lifelog_processing_queue')
RECONNECT_DELAY = int(os.getenv("RECONNECT_DELAY_SECONDS", 5))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "user")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "password")



def store_raw_events(db_session: SQLAlchemySession, payload: InputLogPayload) -> List[EventOrm]:
    """
    Stores raw events from the payload into the 'events' and typed data tables.
    It filters out events that have already been stored based on a payload hash.
    Returns a list of the newly created Event ORM objects.
    """
    # 1. Deduplicate events within the payload itself (by hash)
    seen_hashes = set()
    unique_events = []
    for raw_event in payload.events:
        event_dict = raw_event.model_dump(mode='json')
        payload_str = json.dumps(event_dict, sort_keys=True)
        payload_hash = hashlib.md5(payload_str.encode()).hexdigest()
        if payload_hash in seen_hashes:
            logger.debug(f"Duplicate event in payload (hash {payload_hash[:8]}), skipping within batch.")
            continue
        seen_hashes.add(payload_hash)
        unique_events.append((raw_event, payload_hash))

    # 2. Log DB state before inserting
    db_count = db_session.query(EventOrm).count()
    logger.info(f"Events in DB before insert: {db_count}")
    logger.info(f"Attempting to insert {len(unique_events)} unique events from payload.")

    newly_created_events = []
    for raw_event, payload_hash in unique_events:
        # Check if an event with this hash already exists
        if db_session.query(EventOrm.id).filter(EventOrm.payload_hash == payload_hash).first():
            logger.debug(f"Skipping duplicate event with hash {payload_hash[:8]} (already in DB)...")
            continue

        event = EventOrm(
            id=uuid.uuid4(),
            event_type=EventKind.DIGITAL_ACTIVITY,  # Use Enum member, not .value
            source=payload.source_id,
            start_time=raw_event.timestamp,
            end_time=raw_event.timestamp + timedelta(seconds=raw_event.data.get("duration_seconds", 1)),
            payload_hash=payload_hash,
            details=raw_event.data
        )

        event.digital_activity = DigitalActivityData(
            hostname=payload.source_id,
            app=raw_event.data.get("app"),
            title=raw_event.data.get("title"),
            url=raw_event.data.get("url")
        )
        logger.debug(f"Adding event with hash {payload_hash[:8]} to session.")
        db_session.add(event)
        newly_created_events.append(event)

    if not newly_created_events:
        logger.info("No new events to insert after deduplication and DB check.")
        return []

    try:
        db_session.flush() # Flush to check for errors and assign IDs
        logger.info(f"Stored {len(newly_created_events)} new raw events in the database.")
        return newly_created_events
    except IntegrityError as e:
        logger.error(f"Integrity error while storing raw events. Rolling back this batch. Error: {e}")
        db_session.rollback()
        return []




def process_ingestion_message(channel, method, properties, body):
    """
    Callback function to process a message from the ingestion queue.

    Args:
        channel: The channel object.
        method: The method frame.
        properties: The properties of the message.
        body: The message body.
    """
    logger.info(f"Received ingestion message with delivery tag {method.delivery_tag}")

    try:
        input_payload = InputLogPayload.model_validate(json.loads(body.decode('utf-8')))
        
        if not input_payload.events:
            logger.info("Ingestion payload contains no events. Acknowledging message.")
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        with get_db_session() as db_session:
            new_events = store_raw_events(db_session, input_payload)
            if not new_events:
                logger.info("No new events to process (all duplicates). Acknowledging.")
                channel.basic_ack(delivery_tag=method.delivery_tag)
                return
        
        logger.info(f"Successfully stored {len(new_events)} new events from ingestion.")
        channel.basic_ack(delivery_tag=method.delivery_tag)

    except (ValidationError, json.JSONDecodeError) as e:
        logger.error(f"Unrecoverable data error for ingestion message {method.delivery_tag}: {e}. Discarding.")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except (SQLAlchemyError, AMQPConnectionError) as e:
        logger.error(f"Recoverable error on ingestion message {method.delivery_tag}: {e}. Requeuing.", exc_info=True)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    except Exception as e:
        logger.error(f"Unexpected error on ingestion message {method.delivery_tag}: {e}", exc_info=True)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def process_processing_message(channel, method, properties, body):
    """
    Callback function to process a message from the processing queue.

    Args:
        channel: The channel object.
        method: The method frame.
        properties: The properties of the message.
        body: The message body.
    """
    logger.info(f"Received processing request with delivery tag {method.delivery_tag}")

    try:
        request_payload = ProcessingRequestPayload.model_validate_json(body)
        
        logger.info(f"Processing request for date: {request_payload.target_date}")
        
        # Run the batch processing for the given day, overriding the schedule check
        import asyncio
        asyncio.run(run_batch_processing(request_payload.target_date, process_at_utc=datetime.now(timezone.utc)))
        
        logger.info(f"Successfully completed processing for {request_payload.target_date}.")
        channel.basic_ack(delivery_tag=method.delivery_tag)

    except (ValidationError, json.JSONDecodeError) as e:
        logger.error(f"Unrecoverable data error for processing message {method.delivery_tag}: {e}. Discarding.")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        logger.error(f"Unexpected error during on-demand processing for message {method.delivery_tag}: {e}", exc_info=True)
        # Requeueing might cause repeated failures if the error is deterministic.
        # For now, we discard it to prevent a poison-pill scenario.
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main():
    """Main function to connect to RabbitMQ and start consuming messages."""
    connection = None

    logger.info("Worker starting up...")
    logger.info("Performing database connection check...")
    if not check_db_connection():
        logger.error("Initial database connection failed. Please check DB settings. Worker will not start.")
        return
    logger.info("Initial database connection successful.")

    while True:
        try:
            logger.info(f"Attempting to connect to RabbitMQ at {RABBITMQ_HOST}:{RABBITMQ_PORT}...")
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            connection = pika.BlockingConnection(pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            ))
            channel = connection.channel()
            
            # Declare both queues
            channel.queue_declare(queue=INGESTION_QUEUE, durable=True)
            channel.queue_declare(queue=PROCESSING_QUEUE, durable=True)
            logger.info(f"Declared queues: '{INGESTION_QUEUE}' and '{PROCESSING_QUEUE}'.")

            channel.basic_qos(prefetch_count=1)
            
            # Set up consumers for both queues
            channel.basic_consume(queue=INGESTION_QUEUE, on_message_callback=process_ingestion_message)
            channel.basic_consume(queue=PROCESSING_QUEUE, on_message_callback=process_processing_message)
            
            logger.info("Starting to consume messages from both queues...")
            channel.start_consuming()
        except AMQPConnectionError as e:
            logger.error(f"Connection to RabbitMQ failed: {e}. Retrying in {RECONNECT_DELAY} seconds...")
            time.sleep(RECONNECT_DELAY)
        except KeyboardInterrupt:
            logger.info("Worker stopped by user.")
            if connection and connection.is_open:
                connection.close()
            break
        except Exception as e:
            logger.error(f"An unexpected error occurred in main loop: {e}. Retrying...", exc_info=True)
            if connection and connection.is_open:
                connection.close()
            time.sleep(RECONNECT_DELAY)


if __name__ == '__main__':
    main()
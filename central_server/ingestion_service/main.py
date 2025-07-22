import logging
import datetime
import os
import json
import aio_pika
from aio_pika import Message, DeliveryMode
from aio_pika.exceptions import AMQPException
from fastapi import FastAPI, HTTPException
from typing import Dict, Any
from dotenv import load_dotenv

from models import LogPayload

load_dotenv()

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# RabbitMQ Configuration
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "lifelog_events_queue")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "user")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "password")

app = FastAPI(
    title="Data Ingestion Service",
    description="Receives data from local daemons, validates it, and publishes it to a RabbitMQ queue.",
    version="0.2.0"
)

async def publish_to_rabbitmq(payload: LogPayload) -> bool:
    """Publish the validated payload to RabbitMQ asynchronously."""
    try:
        connection = await aio_pika.connect_robust(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            login=RABBITMQ_USER,
            password=RABBITMQ_PASS,
        )
        async with connection:
            channel = await connection.channel()
            await channel.declare_queue(RABBITMQ_QUEUE, durable=True)

            message_body = payload.model_dump_json().encode()
            await channel.default_exchange.publish(
                Message(
                    body=message_body,
                    delivery_mode=DeliveryMode.PERSISTENT,
                ),
                routing_key=RABBITMQ_QUEUE,
            )
        logger.info(
            f"Successfully published message for source_id: {payload.source_id} to queue '{RABBITMQ_QUEUE}'"
        )
        return True
    except AMQPException as e:
        logger.error(
            f"Failed to connect or publish to RabbitMQ at {RABBITMQ_HOST}:{RABBITMQ_PORT}. Error: {e}"
        )
        return False
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during RabbitMQ publishing: {e}",
            exc_info=True,
        )
        return False

@app.post("/api/v1/ingest")
async def ingest_data(payload: LogPayload) -> Dict[str, Any]:
    """
    Receives data from local daemons.
    - Validates the incoming JSON payload against the LogPayload model.
    - Publishes the validated data to a RabbitMQ queue.
    """
    ingestion_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        # Pydantic performs validation automatically when the payload is type-hinted.
        # If validation fails, FastAPI will return a 422 Unprocessable Entity error.

        logger.info(
            f"Received data batch at {ingestion_timestamp} from source_id: {payload.source_id}. "
            f"Number of events: {len(payload.events)}"
        )
        # Log individual events for debugging if needed (can be verbose)
        # for i, event in enumerate(payload.events):
        #     logger.debug(f"Event {i+1}: Timestamp={event.timestamp}, Type={event.type}, Data={event.data}")

        # Publish to RabbitMQ
        if await publish_to_rabbitmq(payload):
            return {
                "status": "success",
                "message": "Data received and published to RabbitMQ.",
                "source_id": payload.source_id,
                "received_events": len(payload.events),
                "ingestion_timestamp": ingestion_timestamp
            }
        else:
            # If publishing failed, it's already logged. Return an error response.
            raise HTTPException(
                status_code=503, # Service Unavailable
                detail="Failed to publish data to message queue. Please try again later."
            )

    except HTTPException as http_exc:
        # Re-raise HTTPException directly (e.g., Pydantic validation errors)
        logger.error(f"HTTPException during ingest: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.error(f"Unexpected error processing ingest request from source_id {getattr(payload, 'source_id', 'unknown')}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Data Ingestion Service is running. POST data to /api/v1/ingest"}

if __name__ == "__main__":
    import uvicorn
    # This is for local development. For production, use a proper ASGI server like Gunicorn with Uvicorn workers.
    # Run from central_server/ingestion_service directory: uvicorn main:app --reload --port 8001
    logger.info(f"Starting Ingestion Service. RabbitMQ configured at: {RABBITMQ_HOST}:{RABBITMQ_PORT}, queue: {RABBITMQ_QUEUE}")
    uvicorn.run(app, host="0.0.0.0", port=8001)
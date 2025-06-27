import pika
import json
import logging
from typing import Dict, Any
from datetime import datetime
from pika.exceptions import AMQPConnectionError

from .core.settings import settings
from . import schemas

logger = logging.getLogger(__name__)

class RabbitMQPublisher:
    """RabbitMQ publisher for sending messages to the processing queue"""
    
    def __init__(self):
        self.connection = None
        self.channel = None
    
    def connect(self) -> bool:
        """Connect to RabbitMQ"""
        try:
            credentials = pika.PlainCredentials(settings.RABBITMQ_USER, settings.RABBITMQ_PASS)
            parameters = pika.ConnectionParameters(
                host=settings.RABBITMQ_HOST,
                port=settings.RABBITMQ_PORT,
                credentials=credentials
            )
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Declare the queue
            self.channel.queue_declare(queue=settings.RABBITMQ_QUEUE, durable=True)
            
            logger.info(f"Connected to RabbitMQ at {settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}")
            return True
        except AMQPConnectionError as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to RabbitMQ: {e}")
            return False
    
    def publish_message(self, payload: schemas.LogPayload) -> bool:
        """Publish a message to RabbitMQ"""
        if not self.connection or self.connection.is_closed:
            if not self.connect():
                return False
        
        if not self.channel:
            logger.error("RabbitMQ channel is not available")
            return False
        
        try:
            message = payload.model_dump_json()
            self.channel.basic_publish(
                exchange='',
                routing_key=settings.RABBITMQ_QUEUE,
                body=message,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                    timestamp=int(datetime.utcnow().timestamp())
                )
            )
            logger.info(f"Published message to queue {settings.RABBITMQ_QUEUE}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish message to RabbitMQ: {e}")
            return False
    
    def close(self):
        """Close the RabbitMQ connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger.info("RabbitMQ connection closed")

# Global publisher instance
rabbitmq_publisher = RabbitMQPublisher()

async def publish_to_rabbitmq(payload: schemas.LogPayload) -> bool:
    """Publish a log payload to RabbitMQ"""
    return rabbitmq_publisher.publish_message(payload)

async def check_rabbitmq_connection() -> bool:
    """Check if RabbitMQ is accessible"""
    try:
        temp_publisher = RabbitMQPublisher()
        result = temp_publisher.connect()
        temp_publisher.close()
        return result
    except Exception as e:
        logger.error(f"RabbitMQ connection check failed: {e}")
        return False

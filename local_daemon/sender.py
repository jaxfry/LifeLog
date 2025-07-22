"""
Data Sender for the Local Daemon.
Sends batched events from the local cache to the central server.
"""
import logging
import json
import time
from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta

import requests # Using requests library for HTTP communication

from . import config
from . import cache

log = logging.getLogger(__name__)

CENTRAL_SERVER_URL = config.CENTRAL_SERVER_ENDPOINT

def format_payload(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Formats the list of events into the JSON payload structure expected by the server.
    """
    payload_events = []
    for event in events:
        # Construct a new dict that strictly matches the LogEvent model on the server
        new_event = {
            "timestamp": event.get("timestamp"),
            "type": event.get("event_type"), # The ingestion API expects 'type'
            "data": event.get("data", {})     # The nested data dictionary
        }
        payload_events.append(new_event)

    return {
        "source_id": config.DEVICE_ID,
        "sent_at_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "events": payload_events
    }

def send_data_to_server(events: List[Dict[str, Any]]) -> bool:
    """
    Sends a batch of events to the central server.
    Returns True on successful transmission (e.g., HTTP 2xx response), False otherwise.
    """
    if not events:
        log.info("No events to send.")
        return True # Considered success as there's nothing to do

    payload = format_payload(events)
    
    headers = {
        "Content-Type": "application/json",
        # Potentially add an API key or auth token here in the future
        "Authorization": f"Bearer {config.SERVER_AUTH_TOKEN}" 
    }

    log.info(f"Attempting to send {len(events)} events to {CENTRAL_SERVER_URL}")
    
    current_retry = 0
    while current_retry <= config.MAX_SEND_RETRIES:
        try:
            # Custom JSON encoder to handle datetime objects
            class DateTimeEncoder(json.JSONEncoder):
                def default(self, o):
                    if isinstance(o, datetime):
                        return o.isoformat()
                    return super().default(o)
            response = requests.post(CENTRAL_SERVER_URL, data=json.dumps(payload, cls=DateTimeEncoder), headers=headers, timeout=30) # 30s timeout
            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
            
            log.info(f"Successfully sent batch of {len(events)} events. Server response: {response.status_code}")
            # Assuming server returns JSON, you could log response.json() if useful
            return True
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP error sending data (attempt {current_retry+1}/{config.MAX_SEND_RETRIES+1}): {e.response.status_code} - {e.response.text}", exc_info=True)
            # For specific client errors (4xx), retrying might not help
            if 400 <= e.response.status_code < 500:
                log.error("Client-side error (4xx). Not retrying this batch.")
                # Depending on the error, these events might need to be quarantined or handled differently.
                # For now, we'll treat it as a failure for this batch.
                return False 
        except requests.exceptions.ConnectionError as e:
            log.error(f"Connection error sending data (attempt {current_retry+1}/{config.MAX_SEND_RETRIES+1}): {e}", exc_info=True)
        except requests.exceptions.Timeout as e:
            log.error(f"Timeout error sending data (attempt {current_retry+1}/{config.MAX_SEND_RETRIES+1}): {e}", exc_info=True)
        except requests.exceptions.RequestException as e: # Catch-all for other requests issues
            log.error(f"Error sending data (attempt {current_retry+1}/{config.MAX_SEND_RETRIES+1}): {e}", exc_info=True)
        except json.JSONDecodeError as e: # Should not happen if payload is well-formed
            log.error(f"Error serializing payload for server: {e}", exc_info=True)
            return False # Non-recoverable for this batch

        current_retry += 1
        if current_retry <= config.MAX_SEND_RETRIES:
            log.info(f"Will retry sending in {config.RETRY_DELAY_SECONDS} seconds...")
            time.sleep(config.RETRY_DELAY_SECONDS)
        else:
            log.error(f"Max retries ({config.MAX_SEND_RETRIES}) reached for sending batch. Giving up on this batch for now.")
            return False
            
    return False # Should be covered by loop logic, but as a fallback

def attempt_send_cached_data():
    """
    Retrieves a batch of events from the cache and attempts to send them.
    If successful, deletes the sent events from the cache.
    """
    log.debug("Checking cache for events to send...")
    
    events_to_send = cache.get_batched_events(limit=config.MAX_BATCH_SIZE)
    
    if not events_to_send:
        log.debug("No events in cache to send.")
        return

    log.info(f"Retrieved {len(events_to_send)} events from cache for sending.")
    
    if send_data_to_server(events_to_send):
        event_cache_ids = [event["cache_id"] for event in events_to_send]
        if cache.delete_events_from_cache(event_cache_ids):
            log.info(f"Successfully sent and deleted {len(event_cache_ids)} events from cache.")
        else:
            log.error(f"Sent {len(event_cache_ids)} events, but failed to delete them from cache. They might be resent.")
    else:
        log.warning(f"Failed to send batch of {len(events_to_send)} events. They remain in cache and will be retried later.")
        # Note: get_batched_events already increments send_attempts.
        # Further logic could be added here to handle events that consistently fail to send
        # (e.g., moving to a 'dead letter' queue after too many attempts).

if __name__ == '__main__':
    # Basic test for the sender
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s")
    
    # For testing, you might want to mock 'requests.post' and 'cache' functions
    # or set up a dummy server endpoint.
    
    # Example: Add some dummy data to cache first
    try:
        cache.initialize_cache()
        # Add a few dummy events if cache is empty
        if cache.get_cache_size() == 0:
            log.info("Adding dummy events to cache for sender test...")
            dummy_events_data = [
                {"app": "TestApp1", "title": "Doing Work", "duration_seconds": 60},
                {"app": "TestApp2", "title": "Browsing", "url": "http://example.com", "duration_seconds": 120},
            ]
            for i, data in enumerate(dummy_events_data):
                ts = datetime.now(timezone.utc) - timedelta(minutes=i*10)
                event = {
                    "event_hash": f"dummy_hash_{i}_{ts.timestamp()}",
                    "timestamp": ts,
                    "event_type": "desktop_activity.window" if "url" not in data else "browser_activity.web",
                    "source": "test_sender",
                    "device_id": config.DEVICE_ID,
                    "data": data
                }
                cache.add_event_to_cache(event)
        log.info(f"Cache size before sending: {cache.get_cache_size()}")
    except Exception as e:
        log.error(f"Error preparing cache for sender test: {e}")
        exit(1)

    log.info("Running manual sender test...")
    # Note: This will attempt to send to the actual configured endpoint.
    # For a real unit test, mock `requests.post`.
    attempt_send_cached_data()
    log.info("Manual sender test finished.")
    log.info(f"Cache size after sending: {cache.get_cache_size()}")

import time
import threading
import requests
import hashlib
import json
import logging
from datetime import datetime
from typing import List, Dict, Any
from .config import config_manager
from .database import db_manager

logger = logging.getLogger(__name__)

class SyncEngine:
    def __init__(self, interval: int = 30):
        self.interval = interval
        self.running = False
        self.thread: threading.Thread = None
        self._stop_event = threading.Event()

    def start(self):
        if self.running:
            return
        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("SyncEngine started.")

    def stop(self):
        if not self.running:
            return
        self.running = False
        self._stop_event.set()
        if self.thread:
            self.thread.join()
        logger.info("SyncEngine stopped.")

    def _run_loop(self):
        while not self._stop_event.is_set():
            if config_manager.is_configured:
                try:
                    self._sync_batch()
                except Exception as e:
                    logger.error(f"Sync error: {e}")
            
            # Sleep for interval or until stopped
            if self._stop_event.wait(self.interval):
                break

    def _sync_batch(self):
        batch = db_manager.pop_batch(limit=50)
        if not batch:
            return

        server_url = config_manager.get("server_url")
        device_id = config_manager.get("device_id")
        api_key = config_manager.get("api_key")
        
        headers = {
            "Content-Type": "application/json",
            # "Authorization": f"Bearer {api_key}" # Assuming Bearer auth or similar
        }

        successful_ids = []

        for item in batch:
            payload = item["payload"]
            payload_str = json.dumps(payload, sort_keys=True)
            payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()
            
            # Add hash to headers as per architecture doc
            item_headers = headers.copy()
            item_headers["X-Payload-Hash"] = payload_hash

            now = datetime.now().astimezone()
            ingest_data = {
                "device_id": device_id,
                "extension_id": item["extension_id"],
                "payload": payload,
                "client_timestamp": now.isoformat(),
                "timezone_offset": now.strftime('%z')
            }

            try:
                response = requests.post(
                    f"{server_url}/api/v1/ingest",
                    json=ingest_data,
                    headers=item_headers,
                    timeout=10
                )

                if response.status_code in [200, 201]:
                    successful_ids.append(item["id"])
                else:
                    logger.warning(f"Failed to ingest item {item['id']}: {response.status_code} - {response.text}")
                    # Simple exponential backoff could be implemented here or at the loop level
                    # For now, we just don't add it to successful_ids so it stays in DB
            except requests.RequestException as e:
                logger.error(f"Network error during ingest: {e}")
                # Stop processing this batch on network error to avoid repeated timeouts
                break

        if successful_ids:
            db_manager.delete_batch(successful_ids)
            logger.info(f"Successfully synced {len(successful_ids)} items.")

sync_engine = SyncEngine()
import time
import threading
import requests
import hashlib
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from .config import config_manager
from .database import db_manager

logger = logging.getLogger(__name__)


class SyncEngine:
    def __init__(self, interval: int = 30):
        self.interval = interval
        self.running = False
        self.thread: threading.Thread = None
        self._stop_event = threading.Event()
        self._backoff = 1
        self._max_backoff = 300

    def _reset_backoff(self):
        self._backoff = 1

    def _next_backoff(self):
        self._backoff = min(self._backoff * 2, self._max_backoff)

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
            self.thread.join(timeout=15)
        logger.info("SyncEngine stopped.")

    def _run_loop(self):
        while not self._stop_event.is_set():
            if config_manager.is_configured:
                try:
                    self._sync_batch()
                    self._reset_backoff()
                except Exception as e:
                    logger.error(f"Sync error: {e}")

            wait = self._backoff if self._backoff > self.interval else self.interval
            if self._stop_event.wait(wait):
                break

    def _sync_batch(self):
        batch = db_manager.pop_batch(limit=50)
        if not batch:
            return

        server_url = config_manager.get("server_url")
        api_key = config_manager.get("api_key")

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        }

        successful_ids = []
        network_error = False

        for item in batch:
            payload = item["payload"]
            payload_str = json.dumps(payload, sort_keys=True, default=str)
            payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()

            item_headers = headers.copy()
            item_headers["X-Payload-Hash"] = payload_hash

            now = datetime.now().astimezone()
            ingest_data = {
                "extension_id": item["extension_id"],
                "payload": payload,
                "client_timestamp": now.isoformat(),
                "client_timezone": now.strftime("%z"),
            }

            try:
                response = requests.post(
                    f"{server_url}/api/v1/ingest",
                    json=ingest_data,
                    headers=item_headers,
                    timeout=10,
                )

                if response.status_code in [200, 201]:
                    successful_ids.append(item["id"])
                elif response.status_code in [401, 403]:
                    logger.error(
                        "Auth failed (%d). Stopping sync. Check API key.",
                        response.status_code,
                    )
                    self.running = False
                    break
                else:
                    logger.warning(
                        "Failed item %s: %d - %s",
                        item["id"],
                        response.status_code,
                        response.text[:200],
                    )
            except requests.Timeout:
                logger.error("Request timed out during ingest.")
                network_error = True
                break
            except requests.ConnectionError:
                logger.error("Connection error. Server may be down.")
                network_error = True
                break
            except requests.RequestException as e:
                logger.error(f"Network error during ingest: {e}")
                network_error = True
                break

        if successful_ids:
            db_manager.delete_batch(successful_ids)
            logger.info("Synced %d items.", len(successful_ids))

        if network_error:
            self._next_backoff()
            logger.info("Backing off: %ds", self._backoff)


sync_engine = SyncEngine()

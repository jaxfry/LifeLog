from __future__ import annotations
import asyncio
import time
from typing import Any, Dict, List

from .config import AgentConfig
from .http import DeviceClient
from .queue import OfflineQueue
from .collectors import CollectorSupervisor
from .sync import sync_extensions
from .logging_config import setup_logging
from .retry import RetryManager


async def flush_queue(client: DeviceClient, queue: OfflineQueue, retry_mgr: RetryManager, logger) -> None:
    rows = queue.peek_batch(50)
    if not rows:
        logger.debug("No queued items to flush")
        return
    
    logger.info(f"Flushing {len(rows)} queued item(s)")
    sent_ids: list[int] = []
    for rid, kind, payload in rows:
        try:
            if kind == "ingest":
                await client.ingest(payload["source_actor_slug"], payload["data"])
                logger.debug(f"Sent queued item {rid}")
            sent_ids.append(rid)
        except Exception as e:
            logger.warning(f"Failed to send queued item {rid}: {e}")
            # network or server error, leave in queue
    
    queue.delete_ids(sent_ids)
    if sent_ids:
        logger.info(f"Successfully flushed {len(sent_ids)} item(s)")
        retry_mgr.record_success()
    else:
        logger.error("Failed to flush any items from queue")
        retry_mgr.record_failure()


async def run_agent(cfg: AgentConfig):
    # Setup logging
    logger = setup_logging(verbose=True)  # Can be made configurable
    logger.info("🚀 Starting LifeLog Agent")
    logger.info(f"   Server: {cfg.server_url}")
    logger.info(f"   Platform: {cfg.platform}")
    logger.info(f"   Poll Interval: {cfg.poll_interval_sec}s")
    
    client = DeviceClient(cfg.server_url, cfg.device_key)
    queue = OfflineQueue(max_mb=cfg.max_queue_mb)
    sup = CollectorSupervisor(cfg, client, queue)
    retry_mgr = RetryManager()

    while True:
        # 1) Sync server device config and merge locally
        try:
            logger.debug("Syncing device config from server...")
            server_cfg = await client.get_device_config()
            cfg.merge_server_config(server_cfg)
            cfg.save()
            logger.debug("Device config synced successfully")
            retry_mgr.record_success()
        except Exception as e:
            logger.warning(f"Failed to sync device config: {e}")
            retry_mgr.record_failure()

        # 2) Start/refresh collectors from server extension list
        try:
            logger.debug("Syncing extensions...")
            await sync_extensions(cfg, client, sup)
            logger.debug("Extensions synced successfully")
        except Exception as e:
            logger.warning(f"Failed to sync extensions: {e}")

        # 3) Flush queue
        try:
            await flush_queue(client, queue, retry_mgr, logger)
        except Exception as e:
            logger.error(f"Unexpected error during queue flush: {e}")
            retry_mgr.record_failure()
        
        # Apply backoff if failures detected
        if retry_mgr.consecutive_failures > 0:
            backoff = retry_mgr.backoff_seconds()
            logger.warning(f"⏳ Backing off for {backoff}s due to {retry_mgr.consecutive_failures} consecutive failure(s)")
            await asyncio.sleep(backoff)
        else:
            await asyncio.sleep(cfg.poll_interval_sec)

#!/usr/bin/env python3
"""
ActivityWatch collector for LifeLog agent.

Reads ActivityWatch buckets from the local AW server and emits NDJSON raw_log lines to stdout
with shape: {"type": "raw_log", "data": {"bucket": bucket, "events": [...]}, "external_id": "bucket:event_id"}

**Polling Strategy:**
- Collector polls AW server at interval_sec (default 30s)
- Agent flushes queue to server at poll_interval_sec (default 300s/5min)
- This decouples data collection from network transmission
- Benefits: Resilient to network outages, batches API calls, reduces server load

**Idempotency:**
- Each event includes external_id as "bucket_name:event_id" for server-side deduplication
- No longer maintains local seen_event_ids - server handles deduplication
- This prevents duplicate ingestion after collector restart or reinstall

Configuration via env LIFELOG_COLLECTOR_CONFIG_JSON (JSON):
{
  "aw_base_url": "http://127.0.0.1:5600",
  "buckets": ["aw-watcher-window_<hostname>"],
  "interval_sec": 30
}
If buckets is empty, the collector will discover window buckets automatically.
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from typing import Dict, List, Any, Optional


def _conf() -> tuple[str, List[str], int]:
    cfg_json = os.environ.get("LIFELOG_COLLECTOR_CONFIG_JSON", "{}")
    try:
        cfg = json.loads(cfg_json)
    except Exception:
        cfg = {}
    base = cfg.get("aw_base_url") or "http://127.0.0.1:5600"
    buckets = cfg.get("buckets") or []
    interval = int(cfg.get("interval_sec") or 30)  # Increased from 15s to 30s for better batching
    return base, buckets, interval


def _http_get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _list_buckets(base: str) -> List[str]:
    try:
        data = _http_get_json(base.rstrip("/") + "/api/0/buckets/")
        # AW returns a dict like {"bucket-id": {...}, ...}
        return list(data.keys()) if isinstance(data, dict) else []
    except Exception as e:
        print(json.dumps({"type": "status", "level": "error", "message": f"Failed to list buckets: {e}"}), flush=True)
        return []


def _get_events(base: str, bucket: str, start_iso: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
    """
    Fetch events from an ActivityWatch bucket.
    
    Args:
        base: AW server base URL
        bucket: Bucket ID to query
        start_iso: Optional ISO timestamp to fetch events after
        limit: Maximum events to return (default 500, increased from 100)
               For 30s interval, supports ~16 events/sec sustained
    
    Returns:
        List of event dictionaries
    """
    # AW endpoint: /api/0/buckets/<bucket_id>/events[?start=iso&limit=...]
    url = base.rstrip("/") + f"/api/0/buckets/{urllib.parse.quote(bucket)}/events?limit={limit}"
    if start_iso:
        url += "&start=" + urllib.parse.quote(start_iso)
    try:
        return _http_get_json(url)
    except Exception as e:
        print(json.dumps({"type": "status", "level": "error", "message": f"Failed to get events from {bucket}: {e}"}), flush=True)
        return []


def main() -> None:
    base, buckets, interval = _conf()
    last_ts_per_bucket: dict[str, str] = {}

    print(json.dumps({"type": "status", "message": "activitywatch collector started"}), flush=True)

    while True:
        try:
            # Auto-discover buckets if not specified
            # Collect from multiple bucket types: window, afk, and web (browser activity)
            if buckets:
                bs = buckets
            else:
                all_buckets = _list_buckets(base)
                bs = [
                    b for b in all_buckets 
                    if b.startswith("aw-watcher-window") or    # Window focus events
                       b.startswith("aw-watcher-afk") or       # AFK/active status
                       b.startswith("aw-watcher-web")          # Browser activity (requires aw-watcher-web extension)
                ]
            
            for b in bs:
                start = last_ts_per_bucket.get(b)
                events = _get_events(base, b, start)
                
                if events:
                    # Update last timestamp from the last event
                    last_ts = events[-1].get("timestamp") or events[-1].get("start")
                    if isinstance(last_ts, str):
                        last_ts_per_bucket[b] = last_ts
                    
                    # Send each event individually with external_id for server-side deduplication
                    # This ensures idempotency even if collector restarts or replays data
                    for event in events:
                        event_id = event.get("id")
                        if not event_id:
                            # Skip events without ID - can't guarantee idempotency
                            continue
                        
                        # Create a unique external_id combining bucket and event ID
                        external_id = f"{b}:{event_id}"
                        
                        # Send single event with external_id
                        payload = {"bucket": b, "events": [event]}
                        output = {
                            "type": "raw_log",
                            "data": payload,
                            "external_id": external_id
                        }
                        print(json.dumps(output), flush=True)
        except Exception as e:
            print(json.dumps({"type": "status", "level": "error", "message": str(e)}), flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

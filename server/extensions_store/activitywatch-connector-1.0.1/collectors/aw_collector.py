#!/usr/bin/env python3
"""
ActivityWatch collector for LifeLog agent.

Reads ActivityWatch buckets from the local AW server and emits NDJSON raw_log lines to stdout
with shape: {"type": "raw_log", "data": {"bucket": bucket, "events": [...]}}

Configuration via env LIFELOG_COLLECTOR_CONFIG_JSON (JSON):
{
  "aw_base_url": "http://127.0.0.1:5600",
  "buckets": ["aw-watcher-window_<hostname>"],
  "interval_sec": 15
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
    interval = int(cfg.get("interval_sec") or 15)
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


def _get_events(base: str, bucket: str, start_iso: Optional[str] = None) -> List[Dict[str, Any]]:
    # AW endpoint: /api/0/buckets/<bucket_id>/events[?start=iso&limit=...]
    url = base.rstrip("/") + f"/api/0/buckets/{urllib.parse.quote(bucket)}/events?limit=100"
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
    seen_event_ids: dict[str, set[int]] = {}  # Track seen event IDs per bucket

    print(json.dumps({"type": "status", "message": "activitywatch collector started"}), flush=True)

    while True:
        try:
            bs = buckets or [b for b in _list_buckets(base) if b.startswith("aw-watcher-window")] or []
            for b in bs:
                # Initialize seen set for this bucket if needed
                if b not in seen_event_ids:
                    seen_event_ids[b] = set()
                
                start = last_ts_per_bucket.get(b)
                events = _get_events(base, b, start)
                
                if events:
                    # Filter out events we've already seen (deduplication by ID)
                    new_events = []
                    for event in events:
                        event_id = event.get("id")
                        if event_id and event_id not in seen_event_ids[b]:
                            new_events.append(event)
                            seen_event_ids[b].add(event_id)
                    
                    # Only send if we have new events
                    if new_events:
                        # Update last timestamp from the last NEW event
                        last_ts = new_events[-1].get("timestamp") or new_events[-1].get("start")
                        if isinstance(last_ts, str):
                            last_ts_per_bucket[b] = last_ts
                        
                        payload = {"bucket": b, "events": new_events}
                        print(json.dumps({"type": "raw_log", "data": payload}), flush=True)
                    
                    # Limit memory: keep only last 1000 event IDs per bucket
                    if len(seen_event_ids[b]) > 1000:
                        # Remove oldest half
                        oldest = sorted(seen_event_ids[b])[:500]
                        seen_event_ids[b] -= set(oldest)
        except Exception as e:
            print(json.dumps({"type": "status", "level": "error", "message": str(e)}), flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

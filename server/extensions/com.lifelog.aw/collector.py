import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta

import requests

# Configuration from Environment Variables
API_KEY = os.environ.get("LIFELOG_API_KEY")
SERVER_URL = os.environ.get("LIFELOG_SERVER_URL")
DEVICE_ID = os.environ.get("LIFELOG_DEVICE_ID")
AW_API_URL = "http://localhost:5600/api/0"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

def get_iso_time(dt):
    return dt.replace(microsecond=0).isoformat()

def load_last_synced():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                data = json.load(f)
                ts = data.get("last_synced")
                if ts:
                    return datetime.fromisoformat(ts)
    except Exception as e:
        print(f"Error loading state: {e}", file=sys.stderr)
    return None

def save_last_synced(dt):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({"last_synced": get_iso_time(dt)}, f)
    except Exception as e:
        print(f"Error saving state: {e}", file=sys.stderr)

def main():
    # Log to stderr to avoid polluting stdout (which is for data)
    print(f"Starting ActivityWatch Collector for {DEVICE_ID}...", file=sys.stderr)

    # Start collecting from state or 1 minute ago
    last_synced = load_last_synced()
    if not last_synced:
        last_synced = datetime.now(UTC) - timedelta(minutes=1)
        print("No state found, starting from 1 minute ago.", file=sys.stderr)
    else:
        print(f"Resuming from {last_synced}", file=sys.stderr)

    event_buffer = []
    pending_events = {} # {bucket_id: pending_event_dict}
    last_flush_time = time.time()

    while True:
        try:
            # 1. Get all buckets
            try:
                resp = requests.get(f"{AW_API_URL}/buckets", timeout=5)
            except requests.RequestException:
                print("Could not connect to ActivityWatch. Is it running?", file=sys.stderr)
                time.sleep(30)
                continue

            if resp.status_code != 200:
                print(f"Error polling AW: {resp.status_code}", file=sys.stderr)
                time.sleep(10)
                continue

            buckets = resp.json()
            current_poll_time = datetime.now(UTC)

            for bucket_id, bucket_info in buckets.items():
                # 2. Get events for each bucket since last_synced
                params = {
                    "start": get_iso_time(last_synced),
                    "end": get_iso_time(current_poll_time)
                }

                try:
                    events_resp = requests.get(f"{AW_API_URL}/buckets/{bucket_id}/events", params=params, timeout=10)
                except requests.RequestException:
                    continue

                if events_resp.status_code == 200:
                    events = events_resp.json()

                    # Sort events by timestamp to ensure order
                    # AW usually returns newest first, so we reverse
                    events.sort(key=lambda x: x.get("timestamp", 0))

                    for event in events:
                        ts = event.get("timestamp", 0)
                        dur = event.get("duration", 0)

                        # Construct payload
                        payload = {
                            "source": "activitywatch",
                            "bucket_id": bucket_id,
                            "bucket_type": bucket_info.get("type"),
                            "timestamp": ts,
                            "duration": dur,
                            "data": event.get("data")
                        }

                        # Stateful Buffering Logic
                        pending = pending_events.get(bucket_id)

                        if pending is None:
                            pending_events[bucket_id] = payload
                        else:
                            # Check if title/app (data) matches
                            if pending["data"] == payload["data"]:
                                # Squash: Add duration
                                pending["duration"] += payload["duration"]

                                # If duration > 60s, flush and reset
                                if pending["duration"] > 60:
                                    event_buffer.append(pending)
                                    pending_events[bucket_id] = None
                            else:
                                # No match: Flush pending, set new pending
                                event_buffer.append(pending)
                                pending_events[bucket_id] = payload

            # Update cursor in memory
            last_synced = current_poll_time

            # Flush logic: > 50 events OR > 30 seconds
            time_since_flush = time.time() - last_flush_time
            if len(event_buffer) >= 50 or time_since_flush > 30:
                if event_buffer:
                    print(
                        json.dumps(
                            {"events": event_buffer, "format": "activitywatch.raw.v1"}
                        ),
                        flush=True,
                    )
                    print(f"Flushed {len(event_buffer)} events.", file=sys.stderr)
                    event_buffer = []

                # Save state (checkpoint)
                save_last_synced(last_synced)
                last_flush_time = time.time()

        except Exception as e:
            print(f"Error in collector: {e}", file=sys.stderr)

        time.sleep(10)

if __name__ == "__main__":
    main()

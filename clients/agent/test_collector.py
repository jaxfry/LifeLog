#!/usr/bin/env python3
"""Test the AW collector standalone"""
import subprocess
import sys
import json
import time
import os

config = {
    "aw_base_url": "http://127.0.0.1:5600",
    "interval_sec": 3
}

env = {
    **os.environ,
    "LIFELOG_COLLECTOR_CONFIG_JSON": json.dumps(config),
    "LIFELOG_SOURCE_ACTOR_SLUG": "activitywatch-source"
}

collector_path = "/Users/jaxon/Documents/Coding/LifeLog/server/extensions/activitywatch-connector/collectors/aw_collector.py"

print("🧪 Testing ActivityWatch collector for 10 seconds...")
print(f"Config: {config}")
print()

proc = subprocess.Popen(
    [sys.executable, collector_path],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=env,
    text=True
)

start = time.time()
line_count = 0

try:
    while time.time() - start < 10:
        line = proc.stdout.readline()
        if line:
            line_count += 1
            print(f"[{line_count}] {line.strip()}")
        time.sleep(0.1)
finally:
    proc.terminate()
    proc.wait(timeout=2)
    print(f"\n✅ Collector test complete. Received {line_count} lines.")

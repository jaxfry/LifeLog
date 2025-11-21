import requests
import json
from datetime import datetime, timezone

# 1. Get data from local ActivityWatch (example)
# aw_data = get_activity_watch_data() 
# For now, let's mock it:
mock_aw_payload = {
    "buckets": [
        {
            "id": "aw-watcher-window_test",
            "events": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "duration": 120,
                    "data": {"app": "VS Code", "title": "admin.py - LifeLog"}
                }
            ]
        }
    ]
}

# 2. Send to LifeLog
response = requests.post(
    "http://localhost:8000/api/v1/ingest",
    json={
        "device_id": "macbook-1",
        "extension_id": "com.lifelog.aw", # Must match folder name
        "payload": mock_aw_payload
    }
)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
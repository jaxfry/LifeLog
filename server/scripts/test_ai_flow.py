import requests
import json
import time
import random
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"

def generate_dummy_logs(count=10):
    logs = []
    base_time = datetime.now() - timedelta(hours=1)
    
    for i in range(count):
        # Simulate events every 1 minute
        timestamp = base_time + timedelta(minutes=i)
        
        payload = {
            "timestamp": timestamp.isoformat(),
            "app": "VS Code",
            "window": "main.py - LifeLog",
            "duration": 60
        }
        
        data = {
            "device_id": "test-device-ai-flow",
            "extension_id": "com.lifelog.aw",
            "payload": payload,
            "timezone_offset": "-0800"
        }
        logs.append(data)
    return logs

def test_ai_flow():
    print("\nTesting AI Flow (Ingest -> Sessionize -> Timeline)...")
    
    # 1. Ingest Logs
    logs = generate_dummy_logs(15) # 15 minutes of logs
    print(f"1. Ingesting {len(logs)} logs...")
    
    for log in logs:
        try:
            # Add random hash to payload to ensure uniqueness if needed, 
            # but the server calculates hash from payload.
            # We vary timestamp so hash should be different.
            response = requests.post(f"{BASE_URL}/api/v1/ingest", json=log)
            if response.status_code not in [200, 201]:
                print(f"Error ingesting log: {response.text}")
        except Exception as e:
            print(f"Ingest Error: {e}")
            
    print("Ingestion complete.")
    
    # 2. Trigger Sessionizer & AI
    print("2. Triggering Sessionizer & AI Processing...")
    try:
        response = requests.post(f"{BASE_URL}/api/v1/admin/test/sessionizer")
        if response.status_code == 200:
            sessions = response.json()
            print(f"SUCCESS: Retrieved {len(sessions)} sessions.")
            for s in sessions:
                print(f" - Session {s['id']}: {s['status']}")
                if s.get('timeline_entries'):
                    print(f"   Timeline: {len(s['timeline_entries'])} entries")
        else:
            print(f"FAILURE: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"Processing Error: {e}")

if __name__ == "__main__":
    test_ai_flow()

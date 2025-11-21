import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_processing_flow():
    print("\nTesting Processing Flow...")
    
    # 1. Ingest a log
    payload = {
        "timestamp": str(time.time()),
        "data": "hello world"
    }
    
    data = {
        "device_id": "test-device-01",
        "extension_id": "com.lifelog.test",
        "payload": payload
    }
    
    print("1. Ingesting Log...")
    try:
        response = requests.post(f"{BASE_URL}/api/v1/ingest", json=data)
        print(f"Ingest Response: {response.json()}")
        log_id = response.json().get("id")
    except Exception as e:
        print(f"Ingest Error: {e}")
        return

    if not log_id:
        print("Failed to get log ID")
        return

    # 2. Trigger Processing
    print(f"2. Triggering Processing for Log ID: {log_id}")
    try:
        response = requests.post(f"{BASE_URL}/api/v1/debug/process/{log_id}")
        print(f"Process Response: {response.json()}")
        
        if response.status_code == 200 and response.json().get("events_created") > 0:
            print("SUCCESS: Events created.")
        else:
            print("FAILURE: No events created.")
            
    except Exception as e:
        print(f"Process Error: {e}")

if __name__ == "__main__":
    test_processing_flow()

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_async_processing():
    print("\nTesting Async Processing Flow...")
    
    # 1. Ingest a log
    payload = {
        "timestamp": str(time.time()),
        "data": "async hello world " + str(time.time())
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
        print(f"Log ID: {log_id}")
        print("Check worker logs to confirm processing.")
    except Exception as e:
        print(f"Ingest Error: {e}")

if __name__ == "__main__":
    test_async_processing()

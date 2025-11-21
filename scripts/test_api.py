import requests
import json
import hashlib
import time

BASE_URL = "http://localhost:8000"

def test_root():
    print("Testing Root Endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

def test_ingest():
    print("\nTesting Ingest Endpoint...")
    payload = {
        "timestamp": str(time.time()),
        "data": "Sample log entry " + str(time.time())
    }
    
    data = {
        "device_id": "test-device-01",
        "extension_id": "com.lifelog.test",
        "payload": payload
    }
    
    # First Request
    print("Sending first request...")
    try:
        response = requests.post(f"{BASE_URL}/api/v1/ingest", json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        first_id = response.json().get("id")
    except Exception as e:
        print(f"Error: {e}")
        return

    # Second Request (Duplicate)
    print("Sending duplicate request...")
    try:
        response = requests.post(f"{BASE_URL}/api/v1/ingest", json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        second_id = response.json().get("id")
        
        if first_id == second_id:
            print("SUCCESS: Duplicate detection working (IDs match).")
        else:
            print("FAILURE: IDs do not match.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_root()
    test_ingest()

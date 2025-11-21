import requests
import json

BASE_URL = "http://localhost:8000"

def test_endpoints():
    print("\nTesting Data Endpoints...")
    
    # 1. Get Timeline
    print("\n1. GET /api/v1/timeline")
    try:
        response = requests.get(f"{BASE_URL}/api/v1/timeline?limit=5")
        if response.status_code == 200:
            timelines = response.json()
            print(f"SUCCESS: Retrieved {len(timelines)} timeline entries.")
            for t in timelines:
                print(f" - [{t['start_time']}] {t['activity']}")
        else:
            print(f"FAILURE: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error: {e}")

    # 2. Get Sessions
    print("\n2. GET /api/v1/sessions")
    try:
        response = requests.get(f"{BASE_URL}/api/v1/sessions?limit=5")
        if response.status_code == 200:
            sessions = response.json()
            print(f"SUCCESS: Retrieved {len(sessions)} sessions.")
            for s in sessions:
                print(f" - [{s['start_time']}] Status: {s['status']}")
        else:
            print(f"FAILURE: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_endpoints()

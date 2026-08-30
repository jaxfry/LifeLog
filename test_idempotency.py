#!/usr/bin/env python3
"""
Test script to demonstrate idempotency protection in LifeLog.

This script:
1. Sends the same event multiple times with external_id
2. Verifies only one RawLog is created
3. Tests fingerprint-based deduplication
4. Tests cursor functionality
"""

import asyncio
import httpx
import json
import sys
from datetime import datetime

SERVER_URL = "http://localhost:8000"
API_KEY = "your-device-api-key-here"  # Replace with actual API key


async def test_external_id_idempotency():
    """Test that sending the same event with external_id is idempotent"""
    print("\n=== Test 1: External ID Idempotency ===")
    
    async with httpx.AsyncClient() as client:
        # Create test event data
        event_data = {
            "bucket": "test-bucket",
            "events": [{
                "id": 12345,
                "timestamp": "2024-11-16T12:00:00Z",
                "data": {"app": "TestApp", "title": "Test Window"}
            }]
        }
        
        external_id = "test-bucket:12345"
        
        # Send same event 3 times
        for i in range(3):
            response = await client.post(
                f"{SERVER_URL}/ingest/",
                json={
                    "source_actor_slug": "aw-collector",
                    "data": event_data,
                    "external_id": external_id
                },
                headers={"X-Device-Key": API_KEY}
            )
            
            print(f"Attempt {i+1}: Status {response.status_code}")
            if response.status_code == 201:
                data = response.json()
                print(f"  Raw Log ID: {data.get('raw_log_id')}")
            else:
                print(f"  Error: {response.text}")
        
        print("\n✓ All 3 requests succeeded, but only 1 RawLog should exist in DB")
        print("  (Check server logs for 'Duplicate raw_log detected' messages)")


async def test_fingerprint_idempotency():
    """Test fingerprint-based deduplication when no external_id"""
    print("\n=== Test 2: Fingerprint-Based Idempotency ===")
    
    async with httpx.AsyncClient() as client:
        # Create test event without external_id
        event_data = {
            "bucket": "test-bucket-2",
            "events": [{
                "timestamp": "2024-11-16T13:00:00Z",
                "data": {"app": "AnotherApp", "title": "Another Window"}
            }]
        }
        
        # Send same event 2 times (no external_id, relies on fingerprint)
        for i in range(2):
            response = await client.post(
                f"{SERVER_URL}/ingest/",
                json={
                    "source_actor_slug": "aw-collector",
                    "data": event_data
                    # Note: no external_id - will use fingerprint
                },
                headers={"X-Device-Key": API_KEY}
            )
            
            print(f"Attempt {i+1}: Status {response.status_code}")
            if response.status_code == 201:
                data = response.json()
                print(f"  Raw Log ID: {data.get('raw_log_id')}")
        
        print("\n✓ Both requests succeeded, but only 1 RawLog should exist")
        print("  (Fingerprint deduplication activated)")


async def test_cursor_operations():
    """Test cursor get/update operations"""
    print("\n=== Test 3: Cursor Operations ===")
    
    async with httpx.AsyncClient() as client:
        source_actor = "aw-collector"
        cursor_key = "test-cursor"
        cursor_value = datetime.utcnow().isoformat()
        
        # Update cursor
        print(f"Setting cursor to: {cursor_value}")
        response = await client.put(
            f"{SERVER_URL}/api/v1/device/cursor/{source_actor}/{cursor_key}",
            json={"cursor_value": cursor_value},
            headers={"X-Device-Key": API_KEY}
        )
        
        if response.status_code == 200:
            print("✓ Cursor updated successfully")
            print(f"  Response: {response.json()}")
        else:
            print(f"✗ Failed to update cursor: {response.text}")
            return
        
        # Get cursor
        print("\nRetrieving cursor...")
        response = await client.get(
            f"{SERVER_URL}/api/v1/device/cursor/{source_actor}/{cursor_key}",
            headers={"X-Device-Key": API_KEY}
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✓ Cursor retrieved successfully")
            print(f"  Cursor value: {data.get('cursor_value')}")
            print(f"  Last updated: {data.get('last_updated')}")
            
            if data.get('cursor_value') == cursor_value:
                print("✓ Cursor value matches what we set")
            else:
                print("✗ Cursor value mismatch!")
        else:
            print(f"✗ Failed to retrieve cursor: {response.text}")


async def main():
    print("=" * 60)
    print("LifeLog Idempotency Test Suite")
    print("=" * 60)
    
    if API_KEY == "your-device-api-key-here":
        print("\n⚠️  Please set your API_KEY in the script first!")
        print("   You can create a device via the admin UI or API")
        sys.exit(1)
    
    try:
        # Run tests
        await test_external_id_idempotency()
        await asyncio.sleep(1)
        
        await test_fingerprint_idempotency()
        await asyncio.sleep(1)
        
        await test_cursor_operations()
        
        print("\n" + "=" * 60)
        print("All tests completed!")
        print("=" * 60)
        print("\nTo verify results:")
        print("1. Check server logs for deduplication messages")
        print("2. Query database: SELECT COUNT(*) FROM rawlog WHERE external_id LIKE 'test-%'")
        print("3. Query cursors: SELECT * FROM synccursor WHERE cursor_key = 'test-cursor'")
        
    except httpx.ConnectError:
        print(f"\n✗ Could not connect to server at {SERVER_URL}")
        print("  Make sure the server is running: docker-compose up")
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import sys
import os
import uuid
from datetime import datetime, timedelta, timezone
import json
import hashlib

# Add the parent directory to sys.path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.db import engine
from app.models.data import RawLog, Event

async def seed_data():
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        print("Seeding data...")
        
        # Base time: Today at 9:00 AM
        base_time = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0).replace(tzinfo=None)
        
        # Scenario 1: Commute (GPS) - 09:00 to 09:30
        # We'll create a few GPS points
        for i in range(0, 35, 5): # Every 5 minutes
            timestamp = base_time + timedelta(minutes=i)
            payload = {
                "timestamp": timestamp.isoformat(),
                "latitude": 37.7749,
                "longitude": -122.4194,
                "accuracy": 10
            }
            await create_log_and_event(
                session, 
                "com.lifelog.gps", 
                "location", 
                payload, 
                timestamp
            )

        # Scenario 2: Coding (App Usage) - 09:30 to 11:30
        # Overlaps slightly with commute end (maybe arrived at 9:30)
        coding_start = base_time + timedelta(minutes=30)
        
        # VS Code events
        for i in range(0, 120, 15): # Every 15 minutes check
            timestamp = coding_start + timedelta(minutes=i)
            payload = {
                "timestamp": timestamp.isoformat(),
                "app": "Code",
                "window_title": "main.py - LifeLog",
                "duration": 900 # 15 minutes
            }
            await create_log_and_event(
                session,
                "com.lifelog.aw",
                "app_usage",
                payload,
                timestamp
            )

        # Scenario 3: Lunch (Transaction + GPS) - 12:00 to 13:00
        # Gap from 11:30 to 12:00 (should be a break/gap in sessions)
        lunch_start = base_time + timedelta(hours=3) # 12:00
        
        # Transaction
        trans_payload = {
            "timestamp": lunch_start.isoformat(),
            "merchant": "Starbucks",
            "amount": 8.50,
            "currency": "USD"
        }
        await create_log_and_event(session, "com.lifelog.bank", "transaction", trans_payload, lunch_start)
        
        # GPS at lunch
        gps_payload = {
            "timestamp": lunch_start.isoformat(),
            "latitude": 37.7849,
            "longitude": -122.4094, # Slightly different location
            "label": "Starbucks"
        }
        await create_log_and_event(session, "com.lifelog.gps", "location", gps_payload, lunch_start)

        await session.commit()
        print("Seeding complete.")

async def create_log_and_event(session, ext_id, type, payload, timestamp):
    # Create RawLog
    log_id = uuid.uuid4()
    payload_str = json.dumps(payload, sort_keys=True)
    # Make hash unique per run to avoid collisions if we re-run without clearing
    payload_hash = hashlib.sha256((payload_str + str(uuid.uuid4())).encode()).hexdigest()
    
    raw_log = RawLog(
        id=log_id,
        device_id="seed_device",
        extension_id=ext_id,
        payload=payload,
        received_at=timestamp,
        payload_hash=payload_hash
    )
    session.add(raw_log)
    await session.flush() # Ensure ID is available
    
    # Create Event
    event = Event(
        source_log_id=log_id,
        type=type,
        data=payload,
        created_at=timestamp
    )
    session.add(event)
    return event

if __name__ == "__main__":
    asyncio.run(seed_data())

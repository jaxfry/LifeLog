
import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select, col
from sqlalchemy import desc, and_
from datetime import datetime

# Add server directory to path so imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.dirname(current_dir)
sys.path.append(server_dir)

from app.core.db import engine
from app.models.data import RawLog

async def main():
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # Check for RawLogs received in the last 24 hours (since the issue was reported/fixed)
        # and inspect their payloads to see if they contain data for the gap period.
        
        check_start = datetime(2025, 12, 1, 12, 0) # Check from yesterday noon
        
        stmt = select(RawLog).where(
            col(RawLog.received_at) >= check_start
        ).order_by(col(RawLog.received_at))
        
        result = await session.execute(stmt)
        logs = result.scalars().all()
        
        print(f"Found {len(logs)} RawLogs received since {check_start}:")
        
        gap_start = datetime(2025, 11, 30, 0, 30).timestamp()
        gap_end = datetime(2025, 12, 1, 9, 30).timestamp()
        
        found_gap_data = 0
        
        for log in logs:
            payload = log.payload
            # Payload can be a dict or list of dicts
            items = payload if isinstance(payload, list) else [payload]
            
            for item in items:
                ts = item.get("timestamp")
                if ts:
                    # Timestamp might be ISO string or float/int
                    try:
                        if isinstance(ts, str):
                            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            ts_val = dt.timestamp()
                        else:
                            ts_val = float(ts)
                            
                        if gap_start <= ts_val <= gap_end:
                            found_gap_data += 1
                            if found_gap_data <= 5:
                                print(f"Found gap data! Log {log.id} received at {log.received_at}. Event TS: {ts}")
                    except Exception:
                        pass
                        
        print(f"Total events found falling into the gap period: {found_gap_data}")

if __name__ == "__main__":
    asyncio.run(main())

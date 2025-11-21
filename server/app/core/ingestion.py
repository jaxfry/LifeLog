import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Union, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from app.models.data import RawLog

def calculate_payload_hash(payload: Union[Dict[str, Any], List[Dict[str, Any]]]) -> str:
    """
    Calculates SHA256 hash of the payload.
    Sorts keys to ensure consistent hashing for same content.
    """
    payload_str = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(payload_str.encode('utf-8')).hexdigest()

async def ingest_log(
    session: AsyncSession, 
    device_id: str, 
    extension_id: str, 
    payload: Union[Dict[str, Any], List[Dict[str, Any]]],
    client_timestamp: Optional[datetime] = None,
    timezone_offset: Optional[str] = None
) -> Tuple[RawLog, bool]:
    """
    Ingests a log entry.
    Returns (RawLog, created) tuple.
    created is True if a new log was inserted, False if it was a duplicate.
    """
    payload_hash = calculate_payload_hash(payload)
    
    # Check for duplicate
    statement = select(RawLog).where(
        RawLog.device_id == device_id,
        RawLog.payload_hash == payload_hash
    )
    result = await session.execute(statement)
    existing_log = result.scalars().first()
    
    if existing_log:
        return existing_log, False
    
    # Create new log
    # Ensure client_timestamp is naive local time if it has timezone info
    # We store the local time (naive) and the offset separately.
    if client_timestamp and client_timestamp.tzinfo:
        client_timestamp = client_timestamp.replace(tzinfo=None)

    new_log = RawLog(
        device_id=device_id,
        extension_id=extension_id,
        payload=payload,
        payload_hash=payload_hash,
        client_timestamp=client_timestamp,
        client_timezone=timezone_offset
    )
    session.add(new_log)
    
    try:
        await session.commit()
        await session.refresh(new_log)
        return new_log, True
    except IntegrityError:
        # Race condition: another request inserted the same log between our check and insert
        await session.rollback()
        
        # Fetch the existing log
        result = await session.execute(statement)
        existing_log = result.scalars().first()
        
        if existing_log:
            return existing_log, False
        
        # This shouldn't happen, but re-raise if we can't find the existing log
        raise

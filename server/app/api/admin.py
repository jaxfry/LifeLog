from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from pydantic import BaseModel, ConfigDict
import secrets
import hashlib
import uuid
from app.core.db import get_session
from app.models.config import Device
from app.core.sessionizer import run_sessionizer
from app.core.timeline_processor import process_pending_sessions
from app.models.data import Session

router = APIRouter()

class DeviceCreate(BaseModel):
    name: str
    type: Optional[str] = "unknown"

class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None

class DeviceResponse(BaseModel):
    device_id: str
    api_key: str

class DevicePublic(BaseModel):
    id: str
    name: Optional[str]
    type: Optional[str]
    last_cursor: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

@router.post("/devices", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def register_device(
    device_in: DeviceCreate,
    session: AsyncSession = Depends(get_session)
):
    # Generate Device ID
    # We can use a UUID or a slug. Let's use UUID for uniqueness.
    device_id = str(uuid.uuid4())
    
    # Generate API Key
    api_key = secrets.token_urlsafe(32)
    
    # Hash API Key
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    device = Device(
        id=device_id,
        name=device_in.name,
        type=device_in.type,
        api_key_hash=api_key_hash
    )
    
    session.add(device)
    await session.commit()
    
    return DeviceResponse(device_id=device_id, api_key=api_key)

@router.get("/devices", response_model=List[DevicePublic])
async def list_devices(
    session: AsyncSession = Depends(get_session)
):
    statement = select(Device)
    result = await session.execute(statement)
    return result.scalars().all()

@router.get("/devices/{device_id}", response_model=DevicePublic)
async def get_device(
    device_id: str,
    session: AsyncSession = Depends(get_session)
):
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@router.patch("/devices/{device_id}", response_model=DevicePublic)
async def update_device(
    device_id: str,
    device_in: DeviceUpdate,
    session: AsyncSession = Depends(get_session)
):
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    device_data = device_in.model_dump(exclude_unset=True)
    for key, value in device_data.items():
        setattr(device, key, value)
        
    session.add(device)
    await session.commit()
    await session.refresh(device)
    return device

@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: str,
    session: AsyncSession = Depends(get_session)
):
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    await session.delete(device)
    await session.commit()
    return None

@router.post("/devices/{device_id}/rotate-key", response_model=DeviceResponse)
async def rotate_device_key(
    device_id: str,
    session: AsyncSession = Depends(get_session)
):
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Generate New API Key
    api_key = secrets.token_urlsafe(32)
    
    # Hash API Key
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    device.api_key_hash = api_key_hash
    session.add(device)
    await session.commit()
    
    return DeviceResponse(device_id=device_id, api_key=api_key)

@router.post("/admin/test/sessionizer")
async def test_sessionizer(session: AsyncSession = Depends(get_session)):
    """
    Manually triggers the sessionizer and returns the latest 20 sessions.
    Useful for debugging the session creation logic.
    """
    # 1. Group events into sessions
    await run_sessionizer(session)
    
    # 2. Generate timeline entries (AI)
    await process_pending_sessions(session)
    
    # Fetch the results for today (or just the latest ones)
    # For testing, let's just return the last 20 sessions created
    statement = select(Session).order_by(Session.start_time.desc()).limit(20)
    result = await session.execute(statement)
    sessions = result.scalars().all()
    
    return sessions


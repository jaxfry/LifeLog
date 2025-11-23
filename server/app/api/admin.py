from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from pydantic import BaseModel, ConfigDict
import secrets
import hashlib
import uuid
from app.core.db import get_session
from app.models.config import Device, SystemConfig, User
from app.models.data import Session, DailySummary
from app.core.sessionizer import run_sessionizer
from app.core.timeline_processor import process_pending_sessions
from app.models.data import Session
from app.core.daily_summary import generate_daily_summary
from app.api.deps import get_current_superuser
from app.core.security import get_password_hash

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

class UserCreate(BaseModel):
    username: str
    password: str
    is_superuser: bool = False

class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    is_active: bool
    is_superuser: bool
    created_at: datetime

@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    session: AsyncSession = Depends(get_session),
    # Only superusers can create new users
    current_user: User = Depends(get_current_superuser)
):
    statement = select(User).where(User.username == user_in.username)
    result = await session.execute(statement)
    if result.scalars().first():
        raise HTTPException(
            status_code=400,
            detail="The user with this username already exists in the system.",
        )
    
    user = User(
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password),
        is_superuser=user_in.is_superuser
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user

@router.post("/devices", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def register_device(
    device_in: DeviceCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser)
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
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser)
):
    statement = select(Device)
    result = await session.execute(statement)
    return result.scalars().all()

@router.get("/devices/{device_id}", response_model=DevicePublic)
async def get_device(
    device_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser)
):
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@router.patch("/devices/{device_id}", response_model=DevicePublic)
async def update_device(
    device_id: str,
    device_in: DeviceUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser)
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
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser)
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
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser)
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
async def test_sessionizer(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser)
):
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
    # Note: Session.start_time is a datetime, so .desc() works in SQLAlchemy/SQLModel expressions
    # but type checkers might complain.
    from sqlalchemy import desc
    statement = select(Session).order_by(desc(Session.start_time)).limit(20)
    result = await session.execute(statement)
    sessions = result.scalars().all()
    
    return sessions

class SystemConfigUpdate(BaseModel):
    value: str
    description: Optional[str] = None

@router.get("/config", response_model=List[SystemConfig])
async def list_config(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser)
):
    statement = select(SystemConfig)
    result = await session.execute(statement)
    return result.scalars().all()

@router.put("/config/{key}", response_model=SystemConfig)
async def update_config(
    key: str,
    config_in: SystemConfigUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser)
):
    config = await session.get(SystemConfig, key)
    if not config:
        config = SystemConfig(key=key, value=config_in.value, description=config_in.description)
    else:
        config.value = config_in.value
        if config_in.description:
            config.description = config_in.description
        config.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config

@router.post("/admin/generate-summary/{date_str}")
async def trigger_daily_summary(
    date_str: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser)
):
    """
    Manually triggers daily summary generation for a specific date (YYYY-MM-DD).
    """
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
        # Ensure it's timezone aware (UTC) for the function logic, or naive if that's what the DB expects.
        # The DB stores naive UTC.
        target_date = target_date.replace(tzinfo=None)
        
        await generate_daily_summary(session, target_date)
        
        # Fetch and return the result
        stmt = select(DailySummary).where(DailySummary.date == target_date)
        result = await session.execute(stmt)
        summary = result.scalars().first()
        return summary
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")


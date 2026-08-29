import secrets
from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_session
from app.core.dependencies import Pagination, get_current_superuser
from app.core.security import hash_api_key
from app.models.auth import Device, User

router = APIRouter()


class DeviceCreate(BaseModel):
    id: str
    name: str | None = None
    device_type: str | None = None


class DeviceUpdate(BaseModel):
    name: str | None = None
    device_type: str | None = None
    is_active: bool | None = None


class DeviceResponse(BaseModel):
    id: str
    name: str | None
    device_type: str | None
    is_active: bool
    last_cursor: datetime | None
    created_at: datetime
    api_key: str | None = None


class DevicePublic(BaseModel):
    id: str
    name: str | None
    device_type: str | None
    is_active: bool
    last_cursor: datetime | None
    created_at: datetime
    updated_at: datetime


@router.post("/devices", status_code=status.HTTP_201_CREATED)
async def register_device(
    device_data: DeviceCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser),
):
    existing = await session.get(Device, device_data.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Device with this ID already exists",
        )

    api_key = secrets.token_hex(32)
    api_key_hash = hash_api_key(api_key)

    device = Device(
        id=device_data.id,
        user_id=current_user.id,
        name=device_data.name,
        device_type=device_data.device_type,
        api_key_hash=api_key_hash,
    )
    session.add(device)
    await session.commit()
    await session.refresh(device)

    return DeviceResponse(
        id=device.id,
        name=device.name,
        device_type=device.device_type,
        is_active=device.is_active,
        last_cursor=device.last_cursor,
        created_at=device.created_at,
        api_key=api_key,
    )


@router.get("/devices", response_model=list[DevicePublic])
async def list_devices(
    pagination: Pagination = Depends(),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_superuser),
):
    statement = (
        select(Device)
        .order_by(Device.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    )
    result = await session.execute(statement)
    return result.scalars().all()


@router.get("/devices/{device_id}", response_model=DevicePublic)
async def get_device(
    device_id: str,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_superuser),
):
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.patch("/devices/{device_id}", response_model=DevicePublic)
async def update_device(
    device_id: str,
    device_data: DeviceUpdate,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_superuser),
):
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    update_data = device_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(device, field, value)
    device.updated_at = _utcnow()

    session.add(device)
    await session.commit()
    await session.refresh(device)
    return device


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: str,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_superuser),
):
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await session.delete(device)
    await session.commit()


@router.post("/devices/{device_id}/rotate-key")
async def rotate_device_key(
    device_id: str,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_superuser),
):
    device = await session.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    new_api_key = secrets.token_hex(32)
    device.api_key_hash = hash_api_key(new_api_key)
    device.updated_at = _utcnow()

    session.add(device)
    await session.commit()

    return {"api_key": new_api_key}

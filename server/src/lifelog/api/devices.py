"""
Device Management API

Internal API endpoints for managing devices that can send data to LifeLog.
Devices are authenticated via API keys for the ingestion endpoint.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from .. import schemas, models
from ..dependencies import get_session
from ..services import DeviceService
from ..auth import require_auth

router = APIRouter(prefix="/devices")


@router.post("/", response_model=schemas.DeviceCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    device_data: schemas.DeviceCreate,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    """
    Register a new device and generate an API key.
    
    The API key is returned only once - store it securely!
    This key will be used in the X-Device-Key header for ingestion requests.
    """
    try:
        device, api_key = await DeviceService.create_device(
            session=session,
            name=device_data.name,
            device_type=device_data.type,
            client_metadata=device_data.client_metadata
        )
        
        device_read = schemas.DeviceRead.model_validate(device)
        return schemas.DeviceCreateResponse(**device_read.model_dump(), api_key=api_key)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/", response_model=List[schemas.DeviceRead])
async def list_devices(
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    """
    List all registered devices.
    
    Note: API keys are never returned in list/read endpoints for security.
    """
    devices = await DeviceService.get_all_devices(session)
    return [schemas.DeviceRead.model_validate(device) for device in devices]


@router.get("/{device_id}", response_model=schemas.DeviceRead)
async def get_device(
    device_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    """
    Get details for a specific device.
    
    Note: The API key is never returned for security reasons.
    """
    device = await DeviceService.get_device_by_id(session, device_id)
    
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device with ID {device_id} not found"
        )
    
    return schemas.DeviceRead.model_validate(device)


@router.patch("/{device_id}", response_model=schemas.DeviceRead)
async def update_device(
    device_id: int,
    device_update: schemas.DeviceUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    """
    Update device information (name, type, or metadata).
    
    The API key cannot be changed via this endpoint - use the rotate-key endpoint instead.
    """
    try:
        device = await DeviceService.update_device(
            session=session,
            device_id=device_id,
            name=device_update.name,
            device_type=device_update.type,
            client_metadata=device_update.client_metadata
        )
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device with ID {device_id} not found"
            )
        
        return schemas.DeviceRead.model_validate(device)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    """
    Delete a device.
    
    Warning: This will invalidate the device's API key immediately.
    Any raw logs already ingested from this device will remain in the system.
    """
    deleted = await DeviceService.delete_device(session, device_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device with ID {device_id} not found"
        )
    
    return None


@router.post("/{device_id}/rotate-key", response_model=schemas.DeviceRotateKeyResponse)
async def rotate_device_key(
    device_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    """
    Rotate the API key for a device.
    
    The old key will be invalidated immediately and a new key will be generated.
    Store the new key securely - it won't be shown again!
    """
    try:
        device, new_api_key = await DeviceService.rotate_device_key(session, device_id)
        
        if not device or device.id is None:
            raise ValueError("Device not found or has no ID")

        return schemas.DeviceRotateKeyResponse(
            message=f"API key rotated successfully for device '{device.name}'",
            device_id=device.id,
            new_api_key=new_api_key
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

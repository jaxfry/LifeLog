# Implementation Guide: API Authentication

**Priority:** CRITICAL  
**Estimated Time:** 8 hours  
**Difficulty:** Medium

---

## Overview

Currently, the LifeLog API is open to anyone. Device API keys are generated when devices are registered, but they are never validated on incoming requests. This guide walks through implementing proper authentication.

---

## Current State

**Device Registration Flow (Working):**
```python
# server/app/api/admin.py - Line 41
@router.post("/devices", response_model=DeviceResponse)
async def register_device(...):
    api_key = secrets.token_urlsafe(32)  # Generated ✅
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()  # Hashed ✅
    device = Device(..., api_key_hash=api_key_hash)  # Stored ✅
    return DeviceResponse(device_id=device_id, api_key=api_key)
```

**Problem:**
```python
# server/app/api/ingest.py - Line 21
@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_log_entry(
    request: Request,
    ingest_req: IngestRequest,
    session: AsyncSession = Depends(get_session)
):
    # No authentication check! ❌
    log, created = await ingest_log(...)
```

Anyone can post to `/api/v1/ingest` without credentials.

---

## Solution Design

### Architecture

```
Client Request → FastAPI Middleware → Validate API Key → Execute Route Handler
                                    ↓ (if invalid)
                                403 Forbidden
```

### Components

1. **API Key Header:** `X-API-Key: <key>`
2. **Validation Function:** Hash key, check database
3. **FastAPI Dependency:** `Depends(verify_api_key)`
4. **Apply to Routes:** Protected endpoints require authentication

---

## Implementation Steps

### Step 1: Create Authentication Dependency

**File:** `server/app/api/deps.py`

Add to existing file:

```python
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.models.config import Device
import hashlib

# Define the security scheme
api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(
    api_key: str = Security(api_key_header_scheme),
    session: AsyncSession = Depends(get_session)
) -> Device:
    """
    Validate API key and return the associated device.
    Raises 403 if invalid or missing.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key required. Include X-API-Key header."
        )
    
    # Hash the provided key
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    # Look up device by hash
    statement = select(Device).where(Device.api_key_hash == api_key_hash)
    result = await session.execute(statement)
    device = result.scalars().first()
    
    if not device:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )
    
    return device
```

---

### Step 2: Apply to Ingest Endpoint

**File:** `server/app/api/ingest.py`

Add authentication to the ingest endpoint.

---

### Step 3: Update Client

**File:** `lifelog_client/core/sync_engine.py`

Add API key to headers when sending requests.

---

## Testing

### Test Without API Key

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"device_id": "test", "extension_id": "com.test", "payload": {}}'

# Expected: 403 Forbidden
```

### Test With Valid API Key

```bash
# Register device first to get API key
curl -X POST http://localhost:8000/api/v1/devices \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Device"}'

# Use returned API key
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"device_id": "xxx", "extension_id": "com.test", "payload": {}}'

# Expected: 201 Created
```

---

## Security Considerations

1. **Use HTTPS in production** - API keys in headers require encryption
2. **Implement rate limiting** - Prevent brute force attacks
3. **Add audit logging** - Track authentication attempts
4. **Key rotation** - Already implemented via `/devices/{id}/rotate-key`

---

**For complete implementation details, see the full roadmap document.**

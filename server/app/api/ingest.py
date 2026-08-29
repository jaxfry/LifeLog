from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.dependencies import verify_device
from app.core.rate_limit import limiter
from app.models.auth import Device
from app.services.ingestion import ingest_log

router = APIRouter()


class IngestRequest(BaseModel):
    extension_id: str
    payload: dict[str, Any]
    client_timestamp: datetime | None = None
    client_timezone: str | None = None


@router.post("/ingest")
@limiter.limit("60/minute")
async def ingest(
    request: Request,
    body: IngestRequest,
    device: Device = Depends(verify_device),
    session: AsyncSession = Depends(get_session),
):
    raw_log, created = await ingest_log(
        session=session,
        device_id=device.id,
        extension_id=body.extension_id,
        payload=body.payload,
        client_timestamp=body.client_timestamp,
        client_timezone=body.client_timezone,
    )

    if not created:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "duplicate", "id": str(raw_log.id)},
        )

    arq_pool = getattr(request.app.state, "arq_pool", None)
    if arq_pool is not None:
        await arq_pool.enqueue_job("task_normalize_log", str(raw_log.id))

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"status": "created", "id": str(raw_log.id)},
    )

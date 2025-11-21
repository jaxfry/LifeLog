import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.ingestion import ingest_log
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any, Union, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)
router = APIRouter()

class IngestRequest(BaseModel):
    device_id: str
    extension_id: str
    payload: Union[Dict[str, Any], List[Dict[str, Any]]]
    client_timestamp: Optional[datetime] = None
    timezone_offset: Optional[str] = None # e.g. "-0500"

@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_log_entry(
    request: Request,
    ingest_req: IngestRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Ingest log data from a device extension.
    
    Uses payload hash for deduplication - duplicate payloads are automatically skipped.
    Returns 201 for new logs, 200 for duplicates.
    """
    # Validate input
    if not ingest_req.device_id or len(ingest_req.device_id.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="device_id is required"
        )
    
    if not ingest_req.extension_id or len(ingest_req.extension_id.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="extension_id is required"
        )
    
    if not ingest_req.payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload cannot be empty"
        )
    
    log, created = await ingest_log(
        session=session,
        device_id=ingest_req.device_id.strip(),
        extension_id=ingest_req.extension_id.strip(),
        payload=ingest_req.payload,
        client_timestamp=ingest_req.client_timestamp,
        timezone_offset=ingest_req.timezone_offset
    )
    
    if not created:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "skipped", "message": "Log already exists", "id": str(log.id)}
        )
    
    # Enqueue processing task
    if hasattr(request.app.state, "arq_pool"):
        await request.app.state.arq_pool.enqueue_job("task_normalize_log", str(log.id))
    else:
        logger.warning("ARQ pool not available, skipping processing task.")
    
    return {"status": "created", "id": log.id}

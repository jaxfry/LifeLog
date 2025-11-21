from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_session
from app.core.ingestion import ingest_log
from app.core.logger import get_logger
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any, Union, List, Optional
from uuid import UUID

logger = get_logger(__name__)
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
    log, created = await ingest_log(
        session=session,
        device_id=ingest_req.device_id,
        extension_id=ingest_req.extension_id,
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

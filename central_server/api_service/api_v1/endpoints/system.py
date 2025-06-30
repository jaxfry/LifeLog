from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from central_server.api_service.core.database import get_db
from central_server.api_service.core.settings import settings
from central_server.api_service.auth import require_auth
from central_server.api_service import schemas

router = APIRouter()

@router.get("/status", response_model=schemas.SystemStatus)
async def get_system_status(_: str = Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """
    Get the current status of the system.
    Returns system metrics including processing status, last processing time, and service health information.
    """
    # Example: Check DB connection
    database_connected = True
    try:
        await db.execute(text("SELECT 1 FROM timeline_entries LIMIT 1"))
    except Exception:
        database_connected = False
    return schemas.SystemStatus(
        status="ok",
        version=settings.VERSION,
        database_connected=database_connected,
        last_processed_time=None,  # Implement if needed
        events_pending=0,  # Implement if needed
        rabbitmq_connected=True  # Implement if needed
    )

@router.post("/process-now")
async def trigger_processing(_: str = Depends(require_auth)):
    """
    Trigger on-demand processing of all pending events to generate timeline entries.
    This is a placeholder for background processing logic.
    """
    # TODO: Implement actual background processing trigger
    return {"message": "Event processing started in the background (not yet implemented)."}
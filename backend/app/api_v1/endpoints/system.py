from typing import Annotated, Dict, Any, Optional, Callable
import logging
import duckdb
from datetime import datetime
from fastapi import APIRouter, Depends, BackgroundTasks

from backend.app import schemas
from backend.app.core.settings import settings
from backend.app.api_v1.deps import get_db
from backend.app.api_v1.auth import get_current_active_user
from backend.app.processing.timeline import process_pending_events_sync
from backend.app.core.db import get_db_connection

logger = logging.getLogger(__name__)
router = APIRouter()

CurrentUserDep = Annotated[schemas.User, Depends(get_current_active_user)]
DBDep = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]

class ProcessingTaskManager:
    """Manages background processing tasks."""
    
    @staticmethod
    def create_processing_task() -> Callable[[], None]:
        """Create a background task for timeline processing."""
        def processing_task_wrapper():
            """Background task wrapper that manages its own database connection."""
            task_db_conn: Optional[duckdb.DuckDBPyConnection] = None
            
            try:
                logger.info("Background task: Starting on-demand timeline processing...")
                task_db_conn = get_db_connection()
                process_pending_events_sync(task_db_conn, settings)
                logger.info("Background task: On-demand processing complete!")
                
            except Exception as e:
                logger.error(f"Background task: Error during on-demand processing: {e}")
                
            finally:
                if task_db_conn:
                    task_db_conn.close()
                    logger.debug("Background task: Database connection closed.")
        
        return processing_task_wrapper

class SystemStatusService:
    """Service for retrieving system status information."""
    
    @staticmethod
    def get_system_status() -> Dict[str, Any]:
        """
        Get current system status.
        
        Returns:
            Dictionary containing system status information
        """
        last_processed_time = SystemStatusService._get_last_processed_time()
        
        return {
            "processing_status": "idle",  # TODO: Implement actual status tracking
            "last_successful_processing_time": last_processed_time or "N/A",
            "pending_events_count": "N/A",  # TODO: Implement pending events count
            "llm_service_status": "assumed_operational",  # TODO: Implement LLM health check
            "api_version": settings.API_V1_STR,
            "message": "System status is nominal (placeholder values)."
        }
    
    @staticmethod
    def _get_last_processed_time() -> Optional[str]:
        """Get the timestamp of the last successful processing."""
        db_conn: Optional[duckdb.DuckDBPyConnection] = None
        
        try:
            db_conn = get_db_connection(read_only=True)
            result = db_conn.execute("SELECT MAX(processed_at) FROM event_state").fetchone()
            
            if result and result[0]:
                if isinstance(result[0], datetime):
                    return result[0].isoformat()
                return str(result[0])
            
            return None
            
        except Exception as e:
            logger.error(f"Could not fetch last_processed_time for system status: {e}")
            return None
            
        finally:
            if db_conn:
                db_conn.close()

# --- API Endpoints ---

@router.post("/process-now")
async def trigger_processing(
    background_tasks: BackgroundTasks,
    db: DBDep,
    current_user: CurrentUserDep
):
    """
    Trigger on-demand processing of all pending events to generate timeline entries.
    This is a potentially long-running operation and is executed in the background.
    A 202 Accepted response is returned immediately.
    
    Note: In production, consider implementing a lock mechanism to prevent
    concurrent processing tasks.
    """
    processing_task = ProcessingTaskManager.create_processing_task()
    background_tasks.add_task(processing_task)
    
    return {"message": "Event processing started in the background."}

@router.get("/status", response_model=Dict[str, Any])
async def get_system_status(current_user: CurrentUserDep):
    """
    Get the current status of the system.
    
    Returns system metrics including processing status, last processing time,
    and service health information.
    """
    return SystemStatusService.get_system_status()
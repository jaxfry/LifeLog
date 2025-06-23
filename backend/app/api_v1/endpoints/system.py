from typing import Annotated, Dict, Any, Optional
import duckdb
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks

from backend.app import schemas # For response models if any, or general use
from backend.app.core.settings import settings # To pass to processing function
from backend.app.api_v1.deps import get_db
from backend.app.api_v1.auth import get_current_active_user
from backend.app.processing.timeline import process_pending_events_sync # The core processing function

router = APIRouter()

CurrentUserDep = Annotated[schemas.User, Depends(get_current_active_user)]
DBDep = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]

# --- System Endpoints ---

@router.post("/process-now", status_code=status.HTTP_202_ACCEPTED)
async def trigger_processing(
    background_tasks: BackgroundTasks,
    db: DBDep, # Get a fresh DB connection for the background task
    current_user: CurrentUserDep # Ensure only authenticated users can trigger
):
    """
    Trigger on-demand processing of all pending events to generate timeline entries.
    This is a potentially long-running operation and is executed in the background.
    A 202 Accepted response is returned immediately.
    """
    # Note: The API design plan mentioned 409 Conflict if processing is already in progress.
    # Implementing a robust check for "already in progress" requires a locking mechanism
    # or status tracking, which is more involved. For now, we'll allow re-triggering.
    
    # The process_pending_events_sync function is synchronous.
    # To run it in the background with FastAPI, we add it as a background task.
    # For truly long-running tasks that might outlive the server process or need more robust
    # management, a dedicated task queue like Celery would be better.
    
    # IMPORTANT: get_db() provides a connection that is managed per-request.
    # For a background task, we need to ensure it handles its own database connection
    # lifecycle if the original request's connection might close before the task finishes.
    # A simple way is to pass the connection details or have the background task
    # acquire its own connection.
    # However, process_pending_events_sync expects an open connection.
    # The `db: DBDep` here will be closed when this request handler finishes.
    # This is a common pitfall.
    #
    # Solution: The background task itself should manage its DB connection.
    # We will define a wrapper that opens/closes a connection for the sync function.

    def processing_task_wrapper():
        # This function will run in the background.
        # It needs its own database connection.
        # We cannot directly use the 'db' from the endpoint as it will be closed.
        # We also cannot pass 'settings' directly if it's not picklable by some task runners,
        # but for FastAPI's BackgroundTasks, passing it should be fine.
        
        # For simplicity, we'll acquire a new connection within the task.
        # This means `get_db_connection` from `core.db` should be used.
        from backend.app.core.db import get_db_connection as get_fresh_db_connection # Renamed to avoid confusion
        
        task_db_conn: Optional[duckdb.DuckDBPyConnection] = None # Renamed variable
        try:
            print("Background task: Starting on-demand timeline processing...")
            task_db_conn = get_fresh_db_connection()
            process_pending_events_sync(task_db_conn, settings) # Pass the global settings instance
            print("Background task: On-demand processing complete!")
        except Exception as e:
            # Log this error robustly in a real application
            print(f"Background task: Error during on-demand processing: {e}")
        finally:
            if task_db_conn: # Corrected variable name
                task_db_conn.close() # Corrected variable name
                print("Background task: Database connection closed.")

    background_tasks.add_task(processing_task_wrapper)
    
    return {"message": "Event processing started in the background."}


@router.get("/status", response_model=Dict[str, Any])
async def get_system_status(
    current_user: CurrentUserDep # Secure this endpoint
    # db: DBDep # Could be used to fetch actual status from DB if implemented
):
    """
    Get the current status of the system.
    This is a placeholder and should be expanded with actual system status metrics.
    """
    # Placeholder status
    # TODO: Implement actual status checks:
    # - Is a processing task currently running? (Requires a shared state/lock)
    # - Last successful processing timestamp.
    # - Number of pending events.
    # - Daemon status (if applicable and trackable).
    from backend.app.core.db import get_db_connection as get_fresh_db_connection_status
    
    last_processed_time_iso: Optional[str] = None
    db_for_status: Optional[duckdb.DuckDBPyConnection] = None
    try:
        db_for_status = get_fresh_db_connection_status(read_only=True)
        # Get the latest processed_at timestamp from event_state
        latest_event_state_row = db_for_status.execute("SELECT MAX(processed_at) FROM event_state").fetchone()
        if latest_event_state_row and latest_event_state_row[0]:
            # Assuming latest_event_state_row[0] is a datetime object
            last_processed_time_iso = latest_event_state_row[0].isoformat()
    except Exception as e:
        # Log this error properly
        print(f"Could not fetch last_processed_time for system status: {e}")
    finally:
        if db_for_status:
            db_for_status.close()

    return {
        "processing_status": "idle", # Placeholder: "idle", "processing", "error"
        "last_successful_processing_time": last_processed_time_iso or "N/A",
        "pending_events_count": "N/A", # Placeholder: Query events table where not in event_state
        "llm_service_status": "assumed_operational", # Placeholder
        "api_version": settings.API_V1_STR, # Example of using settings
        "message": "System status is nominal (placeholder values)."
    }
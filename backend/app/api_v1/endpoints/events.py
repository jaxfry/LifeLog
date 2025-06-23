import uuid
from typing import List, Optional, Annotated, Dict, Any
from datetime import datetime, date # date for local_day
import duckdb
from fastapi import APIRouter, Depends, HTTPException, status, Query

from backend.app import schemas
from backend.app.api_v1.deps import get_db
from backend.app.api_v1.auth import get_current_active_user

router = APIRouter()

CurrentUserDep = Annotated[schemas.User, Depends(get_current_active_user)]
DBDep = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]

# --- Helper to map DB row to Event schema ---
# This is more complex because 'payload' needs to be fetched from a related table (e.g., digital_activity_data)
# For now, the schema.sql events table does not store the payload directly.
# The API design plan Event model has a 'payload: Dict'.
# The schema.sql events table has 'payload_hash' and specific tables like 'digital_activity_data'
# This implementation will assume for now that we are only querying the 'events' table and the
# 'payload' field in the response schema.Event will be an empty dict or a placeholder,
# as joining and reconstructing the full payload is more involved and depends on event_type.

def _map_event_row_to_schema(db: duckdb.DuckDBPyConnection, row: tuple) -> Optional[schemas.Event]:
    if not row:
        return None
    
    # Current columns from events table as per schema.sql:
    # id, source, event_type, start_time, end_time, payload_hash, local_day
    event_id, source, event_type, start_time, end_time, _payload_hash, local_day_db = row

    # Placeholder for actual payload retrieval based on event_type and event_id
    # This would involve querying other tables like digital_activity_data, etc.
    # For this iteration, payload will be a placeholder.
    actual_payload: Dict[str, Any] = {"placeholder": "Payload data would be here, fetched based on event_type and event_id"}
    
    # If event_type is 'digital_activity', we could try to fetch from digital_activity_data
    if event_type == 'digital_activity':
        try:
            digital_data_row = db.execute(
                "SELECT hostname, app, title, url FROM digital_activity_data WHERE event_id = ?",
                [str(event_id)]
            ).fetchone()
            if digital_data_row:
                actual_payload = {
                    "hostname": digital_data_row[0],
                    "app": digital_data_row[1],
                    "title": digital_data_row[2],
                    "url": digital_data_row[3],
                }
            else:
                actual_payload = {"info": "No detailed digital activity data found for this event_id."}
        except duckdb.Error as e:
            # Log this error, but don't fail the whole event retrieval
            print(f"Error fetching digital_activity_data for event {event_id}: {e}")
            actual_payload = {"error": "Could not fetch detailed payload."}


    return schemas.Event(
        id=event_id,
        source=source,
        event_type=event_type, # This is event_kind from schema.sql
        start_time=start_time,
        end_time=end_time,
        payload=actual_payload, # Placeholder
        local_day=local_day_db
    )

# --- DB Operations for Events ---

def get_event_db(db: duckdb.DuckDBPyConnection, event_id: uuid.UUID) -> Optional[schemas.Event]:
    event_row = db.execute(
        "SELECT id, source, event_type, start_time, end_time, payload_hash, local_day FROM events WHERE id = ?",
        [str(event_id)]
    ).fetchone()
    if event_row:
        return _map_event_row_to_schema(db, event_row)
    return None

def get_events_db(
    db: duckdb.DuckDBPyConnection,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    source: Optional[str] = None,
    event_type: Optional[str] = None, # This corresponds to 'event_kind' in DB
    skip: int = 0,
    limit: int = 100
) -> List[schemas.Event]:
    
    query = "SELECT id, source, event_type, start_time, end_time, payload_hash, local_day FROM events"
    conditions = []
    params = []

    if start_time:
        conditions.append("start_time >= ?")
        params.append(start_time)
    if end_time:
        conditions.append("start_time <= ?") # API plan says end_time, but events have start_time and end_time, so filter on start_time for range
        params.append(end_time)
    if source:
        conditions.append("source = ?")
        params.append(source)
    if event_type:
        conditions.append("event_type = ?") # event_type in schema.Event, event_kind in DB events table
        params.append(event_type)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    # Default sort for events, e.g., by start_time
    query += " ORDER BY start_time DESC" # Or ASC, depending on desired default
    query += " LIMIT ? OFFSET ?"
    params.extend([limit, skip])

    try:
        event_rows = db.execute(query, params).fetchall()
    except duckdb.Error as e:
        # Log error e
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error while fetching events: {e}")

    results: List[schemas.Event] = []
    for row in event_rows:
        if row: # Should always be true
            mapped_event = _map_event_row_to_schema(db, row)
            if mapped_event:
                results.append(mapped_event)
    return results

# --- API Endpoints for Events ---

@router.get("", response_model=List[schemas.Event])
def read_events(
    db: DBDep,
    current_user: CurrentUserDep,
    start_time: Optional[datetime] = Query(None, description="Filter by start time (ISO 8601). Inclusive."),
    end_time: Optional[datetime] = Query(None, description="Filter by end time (ISO 8601). Inclusive of event start times within this."),
    source: Optional[str] = Query(None, description="Filter by event source (e.g., 'activitywatch_aw-watcher-window')."),
    event_type: Optional[str] = Query(None, description="Filter by event type (e.g., 'digital_activity')."), # Maps to DB event_kind
    skip: int = Query(0, ge=0, description="Number of items to skip."),
    limit: int = Query(100, ge=1, le=500, description="Number of items to return.") # Max 500 for events
):
    """
    Retrieve raw events with filtering and pagination.
    Events are generally immutable post-ingestion.
    The 'payload' field currently contains a placeholder or basic data; full payload reconstruction is complex.
    """
    events_list = get_events_db(db, start_time, end_time, source, event_type, skip, limit)
    return events_list

@router.get("/{event_id}", response_model=schemas.Event)
def read_event(
    event_id: uuid.UUID,
    db: DBDep,
    current_user: CurrentUserDep
):
    """
    Get a specific raw event by its ID.
    The 'payload' field currently contains a placeholder or basic data.
    """
    db_event = get_event_db(db, event_id)
    if db_event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return db_event

# POST, PUT, DELETE for events are intentionally omitted as per design plan (events are immutable post-ingestion)
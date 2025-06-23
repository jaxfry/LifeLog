import uuid
from typing import List, Optional, Annotated
from datetime import date, datetime
import duckdb
from fastapi import APIRouter, Depends, HTTPException, status, Path as FastAPIPath # Use FastAPIPath to avoid conflict with standard Path

from backend.app import schemas
from backend.app.api_v1.deps import get_db
from backend.app.api_v1.auth import get_current_active_user
# Import get_timeline_entries_db to reuse logic for fetching entries for a specific day
from backend.app.api_v1.endpoints.timeline import get_timeline_entries_db

router = APIRouter()

CurrentUserDep = Annotated[schemas.User, Depends(get_current_active_user)]
DBDep = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]

# --- Endpoint for Daily Data ---

@router.get("/{date_string}", response_model=schemas.DayDataResponse)
def read_day_data(
    db: DBDep,
    current_user: CurrentUserDep,
    date_string: str = FastAPIPath(..., description="Date in YYYY-MM-DD format.", regex=r"^\d{4}-\d{2}-\d{2}$")
):
    """
    Get all timeline entries and a summary for a specific day.
    The date string must be in YYYY-MM-DD format.
    The daily summary is currently a placeholder.
    """
    try:
        target_date = date.fromisoformat(date_string)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Please use YYYY-MM-DD."
        )

    # Fetch timeline entries for the target date
    # We use the existing get_timeline_entries_db, setting start_date and end_date to the same target_date
    # and fetching all entries for that day (limit can be set high or handled by the function's default)
    timeline_entries_for_day: List[schemas.TimelineEntry] = get_timeline_entries_db(
        db=db,
        start_date=target_date,
        end_date=target_date, # Entries on this specific local_day
        limit=1000 # Assuming a day won't have more than 1000 entries; adjust if needed
    )

    # Placeholder for DailySummary
    # In a real implementation, this would involve fetching or generating a summary.
    # This could involve:
    # 1. Querying a 'daily_summaries' table if summaries are pre-computed.
    # 2. On-the-fly generation using data from timeline_entries_for_day and potentially LLM calls.
    # For now, we return a mock summary as per the schema.
    
    # Example: Calculate some basic stats from the fetched entries for the placeholder
    total_active_min = 0
    focus_time_min = 0 # Define how focus time is determined (e.g. specific projects/activities)
    top_project_counts: dict[str, float] = {}

    for entry in timeline_entries_for_day:
        duration_seconds = (entry.end_time - entry.start_time).total_seconds()
        total_active_min += duration_seconds / 60
        if entry.project and entry.project.name:
            top_project_counts[entry.project.name] = top_project_counts.get(entry.project.name, 0) + (duration_seconds / 60)
            # Example: define "focus_time" as time spent on "LifeLog Development" project
            if entry.project.name == "LifeLog Development":
                 focus_time_min += duration_seconds / 60

    # Get the project name (key) with the maximum time (value)
    top_project_name: Optional[str] = None
    if top_project_counts:
        top_project_name = max(top_project_counts, key=lambda k: top_project_counts[k])


    placeholder_summary = schemas.DailySummary(
        day_summary=f"Placeholder summary for {target_date.isoformat()}. Actual summary generation is pending.",
        stats=schemas.DailySummaryStats(
            total_active_time_min=round(total_active_min),
            focus_time_min=round(focus_time_min), # Placeholder
            number_blocks=len(timeline_entries_for_day),
            top_project=top_project_name, # Placeholder
            top_activity="Placeholder Activity" # Placeholder
        ),
        version=0 # Placeholder version
    )
    
    # Check if data was found for the day (even if summary is placeholder)
    # The API design plan suggests 404 if no data. If entries are empty and summary is just a placeholder,
    # it might be considered "no data".
    if not timeline_entries_for_day and placeholder_summary.stats.number_blocks == 0 : # Crude check
         # Commenting out 404 for now, as even an empty day might be valid to return with a placeholder summary.
         # The frontend might expect a structure even for empty days.
         # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No data found for {target_date.isoformat()}")
         pass


    return schemas.DayDataResponse(
        entries=timeline_entries_for_day,
        summary=placeholder_summary
    )
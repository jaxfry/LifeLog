import uuid
from typing import List, Optional, Annotated, Dict, Any
from datetime import date, datetime
import duckdb
from fastapi import APIRouter, Depends, HTTPException, status, Path as FastAPIPath

from backend.app import schemas
from backend.app.api_v1.deps import get_db
from backend.app.api_v1.auth import get_current_active_user
from backend.app.api_v1.endpoints.timeline import get_timeline_entries_db

router = APIRouter()

CurrentUserDep = Annotated[schemas.User, Depends(get_current_active_user)]
DBDep = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]

class DateValidator:
    """Validates and parses date strings."""
    
    @staticmethod
    def parse_date_string(date_string: str) -> date:
        """
        Parse date string in YYYY-MM-DD format.
        
        Raises:
            HTTPException: If date format is invalid
        """
        try:
            return date.fromisoformat(date_string)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Please use YYYY-MM-DD."
            )

class DayStatsCalculator:
    """Calculates daily statistics from timeline entries."""
    
    @staticmethod
    def calculate_stats(timeline_entries: List[schemas.TimelineEntry]) -> Dict[str, Any]:
        """Calculate basic statistics from timeline entries."""
        total_active_min = 0
        focus_time_min = 0
        project_time_counts: Dict[str, float] = {}
        
        for entry in timeline_entries:
            duration_seconds = (entry.end_time - entry.start_time).total_seconds()
            duration_minutes = duration_seconds / 60
            total_active_min += duration_minutes
            
            if entry.project and entry.project.name:
                project_name = entry.project.name
                project_time_counts[project_name] = project_time_counts.get(project_name, 0) + duration_minutes
                
                # Example: Define "focus_time" as time spent on "LifeLog Development" project
                if project_name == "LifeLog Development":
                    focus_time_min += duration_minutes
        
        top_project_name = DayStatsCalculator._get_top_project(project_time_counts)
        
        return {
            'total_active_time_min': round(total_active_min),
            'focus_time_min': round(focus_time_min),
            'number_blocks': len(timeline_entries),
            'top_project': top_project_name,
            'top_activity': "Placeholder Activity"  # TODO: Implement activity tracking
        }
    
    @staticmethod
    def _get_top_project(project_time_counts: Dict[str, float]) -> Optional[str]:
        """Get the project with the most time spent."""
        if not project_time_counts:
            return None
        return max(project_time_counts.keys(), key=lambda x: project_time_counts[x])

class DailySummaryService:
    """Generates daily summaries."""
    
    @staticmethod
    def create_placeholder_summary(target_date: date, stats: Dict[str, Any]) -> schemas.DailySummary:
        """Create a placeholder daily summary until real implementation is ready."""
        summary_stats = schemas.DailySummaryStats(**stats)
        
        return schemas.DailySummary(
            day_summary=f"Placeholder summary for {target_date.isoformat()}. Actual summary generation is pending.",
            stats=summary_stats,
            version=0
        )

class DayDataService:
    """Service for retrieving and processing day data."""
    
    def __init__(self, db: duckdb.DuckDBPyConnection):
        self.db = db
        self.stats_calculator = DayStatsCalculator()
        self.summary_service = DailySummaryService()
    
    def get_day_data(self, target_date: date) -> schemas.DayDataResponse:
        """
        Get complete day data including timeline entries and summary.
        
        Args:
            target_date: Date to retrieve data for
            
        Returns:
            Complete day data response
        """
        timeline_entries = self._fetch_timeline_entries(target_date)
        stats = self.stats_calculator.calculate_stats(timeline_entries)
        summary = self.summary_service.create_placeholder_summary(target_date, stats)
        
        return schemas.DayDataResponse(
            entries=timeline_entries,
            summary=summary
        )
    
    def _fetch_timeline_entries(self, target_date: date) -> List[schemas.TimelineEntry]:
        """Fetch timeline entries for the specified date."""
        return get_timeline_entries_db(
            db=self.db,
            start_date=target_date,
            end_date=target_date,
            limit=1000  # Assuming a day won't have more than 1000 entries
        )

@router.get("/{date_string}", response_model=schemas.DayDataResponse)
def read_day_data(
    db: DBDep,
    current_user: CurrentUserDep,
    date_string: str = FastAPIPath(
        ..., 
        description="Date in YYYY-MM-DD format.", 
        regex=r"^\d{4}-\d{2}-\d{2}$"
    )
):
    """
    Get all timeline entries and a summary for a specific day.
    The date string must be in YYYY-MM-DD format.
    """
    target_date = DateValidator.parse_date_string(date_string)
    day_service = DayDataService(db)
    return day_service.get_day_data(target_date)
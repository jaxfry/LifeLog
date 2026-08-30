"""
Search API endpoints for semantic event search.
"""
from typing import List, Tuple, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from ..dependencies import get_session
from ..auth import require_auth
from .. import models
from ..services import EmbeddingService

router = APIRouter(prefix="/search", tags=["Search"])

class SearchEventResult(BaseModel):
    id: int
    start_time: str
    end_time: Optional[str]
    event_type: str
    summary: Optional[str]
    distance: float

@router.get("/events", response_model=List[SearchEventResult])
async def search_events(
    q: str = Query(..., alias="q", description="Query text"),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth),
):
    results: list[tuple[models.Event, float]] = await EmbeddingService.search_events_by_text(
        session, query_text=q, limit=limit
    )
    out: list[SearchEventResult] = []
    for event, dist in results:
        if event.id is None:
            # Skip events without IDs (shouldn't happen for persisted rows)
            continue
        # Fetch event type name
        from ..services import TimelineService
        et = await TimelineService.get_event_type_name(session, event.event_type_id)
        out.append(
            SearchEventResult(
                id=event.id,
                start_time=event.start_time.isoformat(),
                end_time=event.end_time.isoformat() if event.end_time else None,
                event_type=et,
                summary=event.summary,
                distance=float(dist),
            )
        )
    return out

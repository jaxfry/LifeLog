from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import or_, select

from app.core.database import get_session
from app.core.dependencies import get_current_superuser, get_current_user
from app.models.auth import User
from app.models.files import ContentChunk, FileAttachment
from app.models.processing import TimelineEntry
from app.services.context import get_owned_area
from app.services.retrieval import (
    backfill_search_documents,
    graph_context,
    retrieve,
    semantic_recall_available,
)

router = APIRouter()


class SearchHitResponse(BaseModel):
    source_type: str
    source_id: str
    title: str | None
    content: str
    occurred_at: datetime | None
    score: float
    reasons: list[str]
    metadata: dict


@router.get("")
async def search(
    q: str = Query(..., min_length=1, max_length=2000),
    limit: int = Query(default=10, ge=1, le=100),
    source_type: list[str] | None = Query(default=None),
    include_graph: bool = True,
    life_area_id: UUID | None = None,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    if life_area_id is not None and await get_owned_area(db_session, life_area_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="Life Area not found")
    hits = await retrieve(
        db_session,
        q,
        limit=limit,
        source_types=set(source_type) if source_type else None,
        user_id=current_user.id,
        area_id=life_area_id,
    )
    graph = (
        await graph_context(
            db_session,
            q,
            limit=limit,
            user_id=current_user.id,
            area_id=life_area_id,
        )
        if include_graph
        else []
    )
    # Compatibility projections also make newly-created, not-yet-indexed rows immediately searchable.
    timeline = [] if life_area_id is not None else (
        await db_session.execute(
            select(TimelineEntry)
            .where(
                TimelineEntry.owner_user_id == current_user.id,
                or_(
                    TimelineEntry.activity.ilike(f"%{q}%"),
                    TimelineEntry.notes.ilike(f"%{q}%"),
                    TimelineEntry.category.ilike(f"%{q}%"),
                )
            )
            .limit(limit)
        )
    ).scalars().all()
    files = [] if life_area_id is not None else (
        await db_session.execute(
            select(FileAttachment)
            .where(
                FileAttachment.owner_user_id == current_user.id,
                or_(
                    FileAttachment.filename.ilike(f"%{q}%"),
                    FileAttachment.description.ilike(f"%{q}%"),
                    FileAttachment.category.ilike(f"%{q}%"),
                )
            )
            .limit(limit)
        )
    ).scalars().all()
    chunks = [] if life_area_id is not None else (
        await db_session.execute(
            select(ContentChunk)
            .join(FileAttachment, FileAttachment.id == ContentChunk.file_id)
            .where(
                FileAttachment.owner_user_id == current_user.id,
                ContentChunk.is_superseded == False,
                ContentChunk.content.ilike(f"%{q}%"),
            )
            .limit(limit)
        )
    ).scalars().all()
    return {
        "query": q,
        "mode": "hybrid" if await semantic_recall_available(db_session) else "lexical_graph",
        "hits": [
            SearchHitResponse(
                source_type=hit.source_type,
                source_id=str(hit.source_id),
                title=hit.title,
                content=hit.content,
                occurred_at=hit.occurred_at,
                score=hit.score,
                reasons=hit.reasons,
                metadata=hit.metadata,
            )
            for hit in hits
        ],
        "graph_facts": graph,
        "timeline": timeline,
        "files": files,
        "content_chunks": chunks,
    }


@router.post("/reindex")
async def reindex(
    limit: int = Query(default=1000, ge=1, le=10_000),
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_superuser),
) -> dict[str, int]:
    counts = await backfill_search_documents(db_session, limit=limit)
    await db_session.commit()
    return counts

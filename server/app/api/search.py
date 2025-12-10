from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, or_
import os
from app.core.db import get_session
from app.core.vector_service import generate_embedding
from app.models.data import Timeline, DailyChapter
from app.models.files import FileAttachment
from app.core.timeline_processor import get_gemini_api_key
from app.core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

@router.get("/")
async def search(
    q: str = Query(..., min_length=1),
    limit: int = 10,
    db: AsyncSession = Depends(get_session)
):
    """
    Hybrid search (Vector + Keyword) across Timeline and DailyChapter entries.
    """
    # 0. Ensure API Key is set for Vector Service
    api_key = await get_gemini_api_key(db)
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key

    # 1. Generate Embedding for Vector Search
    logger.info(f"Generating embedding for search query: '{q}'")
    embedding = await generate_embedding(q)
    
    if embedding:
        logger.info(f"Embedding generated successfully for query: '{q}' (dimension: {len(embedding)})")
    else:
        logger.warning(f"No embedding generated for query: '{q}' - vector search will be skipped")
    
    # --- Timeline Search ---
    timeline_results = {}

    # Vector Search
    if embedding:
        stmt_timeline_vector = select(Timeline).where(Timeline.embedding.is_not(None)).order_by(Timeline.embedding.l2_distance(embedding)).limit(limit)
        result_timeline_vector = await db.execute(stmt_timeline_vector)
        for t in result_timeline_vector.scalars().all():
            timeline_results[t.id] = t

    # Keyword Search
    stmt_timeline_keyword = select(Timeline).where(
        or_(
            Timeline.activity.ilike(f"%{q}%"),
            Timeline.notes.ilike(f"%{q}%"),
            Timeline.category.ilike(f"%{q}%")
        )
    ).limit(limit)
    result_timeline_keyword = await db.execute(stmt_timeline_keyword)
    for t in result_timeline_keyword.scalars().all():
        timeline_results[t.id] = t

    # --- DailyChapter Search ---
    chapter_results = {}

    # Vector Search
    if embedding:
        stmt_chapters_vector = select(DailyChapter).where(DailyChapter.embedding.is_not(None)).order_by(DailyChapter.embedding.l2_distance(embedding)).limit(limit)
        result_chapters_vector = await db.execute(stmt_chapters_vector)
        for c in result_chapters_vector.scalars().all():
            chapter_results[c.id] = c

    # Keyword Search
    stmt_chapters_keyword = select(DailyChapter).where(
        or_(
            DailyChapter.title.ilike(f"%{q}%"),
            DailyChapter.summary.ilike(f"%{q}%"),
            DailyChapter.category.ilike(f"%{q}%")
        )
    ).limit(limit)
    result_chapters_keyword = await db.execute(stmt_chapters_keyword)
    for c in result_chapters_keyword.scalars().all():
        chapter_results[c.id] = c

    # --- FileAttachment Search ---
    file_results = {}

    # Vector Search
    if embedding:
        stmt_files_vector = select(FileAttachment).where(FileAttachment.embedding.is_not(None)).order_by(FileAttachment.embedding.l2_distance(embedding)).limit(limit)
        result_files_vector = await db.execute(stmt_files_vector)
        for f in result_files_vector.scalars().all():
            file_results[f.id] = f

    # Keyword Search
    stmt_files_keyword = select(FileAttachment).where(
        or_(
            FileAttachment.filename.ilike(f"%{q}%"),
            FileAttachment.description.ilike(f"%{q}%"),
            FileAttachment.category.ilike(f"%{q}%")
        )
    ).limit(limit)
    result_files_keyword = await db.execute(stmt_files_keyword)
    for f in result_files_keyword.scalars().all():
        file_results[f.id] = f

    # Convert numpy arrays to lists for JSON serialization
    import numpy as np
    
    final_timeline = []
    for t in timeline_results.values():
        if t.embedding is not None and hasattr(t.embedding, "tolist"):
            t.embedding = t.embedding.tolist()
        final_timeline.append(t)

    final_chapters = []
    for c in chapter_results.values():
        if c.embedding is not None and hasattr(c.embedding, "tolist"):
            c.embedding = c.embedding.tolist()
        final_chapters.append(c)

    final_files = []
    for f in file_results.values():
        if f.embedding is not None and hasattr(f.embedding, "tolist"):
            f.embedding = f.embedding.tolist()
        final_files.append(f)

    return {
        "timeline": final_timeline,
        "chapters": final_chapters,
        "files": final_files
    }

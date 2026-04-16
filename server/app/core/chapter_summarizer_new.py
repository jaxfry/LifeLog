import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from sqlmodel import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.ai_config import completion_with_fallback

from app.models.data import Timeline, DailyChapter
from app.core.prompts import get_chapter_summary_prompt, get_chapter_summary_patch_prompt
from app.core.logger import get_logger
from app.core.vector_service import generate_embedding, get_embedding_model_info


logger = get_logger(__name__)

async def generate_daily_chapters_for_logical_date(db: AsyncSession, logical_date: str):
    """
    Generates or patches high-level chapters for a specific day based on Timeline entries.
    """
    logger.info(f"Generating/Patching daily chapters for {logical_date}...")
    
    # 1. Check if we have existing chapters that look real
    stmt = select(DailyChapter).where(DailyChapter.logical_date == logical_date).order_by(DailyChapter.start_time)
    existing_chapters = (await db.execute(stmt)).scalars().all()
    
    # True if we have real chapters (not just the dummy DIRTY hold)
    is_patch = False
    if existing_chapters and any(c.title != "Pending Chapters" for c in existing_chapters):
        is_patch = True
        
    # 2. Fetch Unsummarized Timeline Entries for this Logical Date
    # Note: we use is_summarized flag. Actually, `generate_daily_summary` marks it is_summarized=True.
    # WAIT! If `generate_daily_summary` marks it True, and we also want chapters to depend on it, 
    # we have a race condition! 
    # That's okay, instead of `is_summarized`, for chapters let's just pick Timeline entries 
    # whose `created_at > max(existing_chapters.last_touched_at)`.
    # Wait, the dummy chapter has last_touched_at = now().

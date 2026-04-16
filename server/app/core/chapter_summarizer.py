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
    logger.info(f"Generating/Patching daily chapters for {logical_date}...")
    
    # 1. Fetch Existing Chapters
    stmt = select(DailyChapter).where(DailyChapter.logical_date == logical_date).order_by(DailyChapter.start_time)
    existing_chapters = (await db.execute(stmt)).scalars().all()
    
    # 2. Are we patching?
    is_patch = existing_chapters and any(c.title != "Pending Chapters" for c in existing_chapters)
    max_updated_at = max((c.updated_at for c in existing_chapters if c.updated_at), default=None)
    
    if max_updated_at:
        # Get NEW timeline entries since last success
        statement = select(Timeline).where(
            Timeline.logical_date == logical_date,
            Timeline.created_at > max_updated_at
        ).order_by(Timeline.start_time)
    else:
        # Full rebuild
        statement = select(Timeline).where(
            Timeline.logical_date == logical_date
        ).order_by(Timeline.start_time)
        
    result = await db.execute(statement)
    entries = result.scalars().all()
    
    if not entries:
        logger.info(f"No new timeline entries found for {logical_date}. Marking as ready.")
        for chap in existing_chapters:
            if chap.processing_status != "ready":
                chap.processing_status = "ready"
                db.add(chap)
        await db.commit()
        return

    user_timezone = entries[0].iana_timezone if entries[0].iana_timezone else "UTC"
    from app.core.utils.time import to_local_time
    
    timeline_json = []
    for entry in entries:
        local_start = to_local_time(entry.start_time, user_timezone)
        local_end = to_local_time(entry.end_time, user_timezone)
        
        timeline_json.append({
            "start": local_start.isoformat(),
            "end": local_end.isoformat(),
            "activity": entry.activity,
            "notes": entry.notes
        })
    
    timeline_str = json.dumps(timeline_json, indent=2)
    
    if is_patch:
        logger.info(f"Patching {len(existing_chapters)} existing chapters for {logical_date} with {len(entries)} new events.")
        
        chapters_json = []
        for chap in existing_chapters:
            if chap.title == "Pending Chapters": continue
            local_start = to_local_time(chap.start_time, user_timezone)
            local_end = to_local_time(chap.end_time, user_timezone)
            chapters_json.append({
                "title": chap.title,
                "summary": chap.summary,
                "start_time": local_start.isoformat(),
                "end_time": local_end.isoformat(),
                "category": chap.category,
                "tags": chap.tags
            })
            
        prompt_template = await get_chapter_summary_patch_prompt(db)
        prompt = prompt_template.format(
            date_str=logical_date,
            user_timezone=user_timezone,
            existing_chapters_json=json.dumps(chapters_json, indent=2),
            timeline_json=timeline_str
        )
    else:
        logger.info(f"Generating full chapters for {logical_date} with {len(entries)} events.")
        prompt_template = await get_chapter_summary_prompt(db)
        prompt = prompt_template.format(
            date_str=logical_date,
            user_timezone=user_timezone,
            timeline_json=timeline_str
        )
    
    try:
        response = await completion_with_fallback(
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content
        
        if content.startswith("```json"): content = content[7:]
        elif content.startswith("```"): content = content[3:]
        if content.endswith("```"): content = content[:-3]
            
        content = content.strip()
        chapters_data = json.loads(content)
        
        # 5. Save Chapters
        # Instead of individually diffing with SQL functions, since we are delta updating the list
        # via the LLM, the LLM returned the ENTIRE NEW LIST. We drop the old ones safely here
        # because the LLM did the heavy lifting of maintaining structure.
        delete_stmt = delete(DailyChapter).where(DailyChapter.logical_date == logical_date)
        await db.execute(delete_stmt)
        
        target_date_local = datetime.strptime(logical_date, "%Y-%m-%d")
        chapter_date = datetime(target_date_local.year, target_date_local.month, target_date_local.day)
        
        now_time = datetime.now(timezone.utc).replace(tzinfo=None)
        
        for chapter in chapters_data:
            try:
                start_time = datetime.fromisoformat(chapter["start_time"].replace("Z", "+00:00"))
                end_time = datetime.fromisoformat(chapter["end_time"].replace("Z", "+00:00"))
                
                if start_time.tzinfo: start_time = start_time.astimezone(timezone.utc).replace(tzinfo=None)
                if end_time.tzinfo: end_time = end_time.astimezone(timezone.utc).replace(tzinfo=None)
                    
                embedding_text = f"Title: {chapter['title']}. Summary: {chapter.get('summary', '')}. Category: {chapter.get('category', '')}. Tags: {', '.join(chapter.get('tags', []))}."
                embedding_vector = await generate_embedding(embedding_text)
                model_info = get_embedding_model_info()

                new_chapter = DailyChapter(
                    date=chapter_date,
                    logical_date=logical_date,
                    start_time=start_time,
                    end_time=end_time,
                    title=chapter["title"],
                    summary=chapter.get("summary"),
                    category=chapter.get("category"),
                    tags=chapter.get("tags", []),
                    embedding=embedding_vector,
                    embedding_model=model_info["model"],
                    embedding_version=model_info["version"],
                    processing_status="ready",
                    updated_at=now_time,
                    last_touched_at=now_time
                )
                db.add(new_chapter)
            except Exception as e:
                logger.error(f"Error parsing chapter data: {e}, data: {chapter}")
                continue
            
        await db.commit()
    except Exception as e:
        logger.error(f"Error generating daily chapters: {e}")
        
async def generate_daily_chapters(db: AsyncSession, target_date: datetime):
    # Try to grab a logical date from the target date naive
    from app.core.utils.time import get_logical_date, get_timezone_obj

    # Just fall back to making logical date from string
    logical_date_str = target_date.strftime("%Y-%m-%d")
    await generate_daily_chapters_for_logical_date(db, logical_date_str)

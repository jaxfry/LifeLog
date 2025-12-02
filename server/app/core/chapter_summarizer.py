import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from sqlmodel import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from litellm import acompletion

from app.models.data import Timeline, DailyChapter
from app.core.prompts import get_chapter_summary_prompt
from app.core.logger import get_logger
from app.core.timeline_processor import get_gemini_api_key
from app.core.vector_service import generate_embedding, EMBEDDING_MODEL, EMBEDDING_VERSION


logger = get_logger(__name__)
MODEL_NAME = "gemini/gemini-flash-latest"

async def generate_daily_chapters(db: AsyncSession, target_date: datetime):
    """
    Generates high-level chapters for a specific day based on Timeline entries.
    """
    logger.info(f"Generating daily chapters for {target_date.date()}...")

    # 1. Determine User Timezone (same logic as daily summary)
    from app.models.data import RawLog
    stmt = select(RawLog.client_timezone).where(RawLog.client_timezone.is_not(None)).order_by(RawLog.received_at.desc()).limit(1)
    result = await db.execute(stmt)
    user_timezone = result.scalar_one_or_none() or "UTC"
    
    from app.core.utils.time import get_day_bounds_utc, to_local_time, get_timezone_obj
    
    # Convert target_date to user's timezone to determine the correct "day"
    if target_date.tzinfo:
        target_date_local = target_date.astimezone(get_timezone_obj(user_timezone))
    else:
        target_date_local = target_date.replace(tzinfo=timezone.utc).astimezone(get_timezone_obj(user_timezone))
    
    # Calculate UTC bounds for the local day
    start_utc, end_utc = get_day_bounds_utc(target_date_local, user_timezone)
    
    # Define start_of_day for chapter date field (Normalized to Midnight, naive datetime for DB)
    chapter_date = datetime(
        target_date_local.year,
        target_date_local.month,
        target_date_local.day,
        0, 0, 0, 0
    )
    
    statement = select(Timeline).where(
        Timeline.start_time >= start_utc,
        Timeline.start_time <= end_utc
    ).order_by(Timeline.start_time)
    
    result = await db.execute(statement)
    entries = result.scalars().all()
    
    if not entries:
        logger.info(f"No timeline entries found for {target_date.date()}.")
        return

    # 2. Prepare Data for LLM
    timeline_json = []
    for entry in entries:
        # Convert to local time for the prompt so AI sees user's actual times
        local_start = to_local_time(entry.start_time, user_timezone)
        local_end = to_local_time(entry.end_time, user_timezone)
        
        timeline_json.append({
            "start": local_start.isoformat(),
            "end": local_end.isoformat(),
            "activity": entry.activity,
            "notes": entry.notes
        })
    
    timeline_str = json.dumps(timeline_json, indent=2)
    
    # 3. Get Prompt
    prompt_template = await get_chapter_summary_prompt(db)
    prompt = prompt_template.format(
        date_str=target_date.strftime("%Y-%m-%d"),
        user_timezone=user_timezone,
        timeline_json=timeline_str
    )
    
    # 4. Call LLM
    try:
        api_key = await get_gemini_api_key(db)
        if not api_key:
             logger.warning("GEMINI_API_KEY not set. Skipping chapter generation.")
             return
        
        os.environ["GEMINI_API_KEY"] = api_key

        response = await acompletion(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content
        
        # Clean up code blocks
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
            
        content = content.strip()
        
        chapters_data = json.loads(content)
        
        # 5. Save Chapters
        # First, delete existing chapters for the day to avoid duplicates/stale data
        # Note: We use delete() with where() clause
        delete_stmt = delete(DailyChapter).where(
            DailyChapter.date == chapter_date
        )
        await db.execute(delete_stmt)
        
        for chapter in chapters_data:
            # Parse times
            try:
                start_time = datetime.fromisoformat(chapter["start_time"].replace("Z", "+00:00"))
                end_time = datetime.fromisoformat(chapter["end_time"].replace("Z", "+00:00"))
                
                # Ensure timezone naive if that's what we store (based on other models)
                if start_time.tzinfo:
                    start_time = start_time.astimezone(timezone.utc).replace(tzinfo=None)
                if end_time.tzinfo:
                    end_time = end_time.astimezone(timezone.utc).replace(tzinfo=None)
                    
                # Generate embedding
                embedding_text = f"Title: {chapter['title']}. Summary: {chapter.get('summary', '')}. Category: {chapter.get('category', '')}. Tags: {', '.join(chapter.get('tags', []))}."
                embedding_vector = await generate_embedding(embedding_text, api_key=api_key)

                new_chapter = DailyChapter(
                    date=chapter_date,
                    start_time=start_time,
                    end_time=end_time,
                    title=chapter["title"],
                    summary=chapter.get("summary"),
                    category=chapter.get("category"),
                    tags=chapter.get("tags", []),
                    embedding=embedding_vector,
                    embedding_model=EMBEDDING_MODEL,
                    embedding_version=EMBEDDING_VERSION
                )
                db.add(new_chapter)
            except Exception as e:
                logger.error(f"Error parsing chapter data: {e}, data: {chapter}")
                continue
            
        await db.commit()
        logger.info(f"Successfully generated {len(chapters_data)} chapters for {target_date.date()}")
        
    except Exception as e:
        logger.error(f"Error generating daily chapters: {e}")
        import traceback
        traceback.print_exc()

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

logger = get_logger(__name__)
MODEL_NAME = "gemini/gemini-flash-latest"

async def generate_daily_chapters(db: AsyncSession, target_date: datetime):
    """
    Generates high-level chapters for a specific day based on Timeline entries.
    """
    logger.info(f"Generating daily chapters for {target_date.date()}...")

    # 1. Fetch Timeline entries for the day
    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    statement = select(Timeline).where(
        Timeline.start_time >= start_of_day,
        Timeline.start_time <= end_of_day
    ).order_by(Timeline.start_time)
    
    result = await db.execute(statement)
    entries = result.scalars().all()
    
    if not entries:
        logger.info(f"No timeline entries found for {target_date.date()}.")
        return

    # 2. Prepare Data for LLM
    timeline_json = []
    for entry in entries:
        timeline_json.append({
            "start": entry.start_time.isoformat(),
            "end": entry.end_time.isoformat(),
            "activity": entry.activity,
            "notes": entry.notes
        })
    
    timeline_str = json.dumps(timeline_json, indent=2)
    
    # 3. Get Prompt
    prompt_template = await get_chapter_summary_prompt(db)
    prompt = prompt_template.format(
        date_str=target_date.strftime("%Y-%m-%d"),
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
            DailyChapter.date >= start_of_day,
            DailyChapter.date <= end_of_day
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
                    
                new_chapter = DailyChapter(
                    date=start_of_day,
                    start_time=start_time,
                    end_time=end_time,
                    title=chapter["title"],
                    summary=chapter.get("summary")
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

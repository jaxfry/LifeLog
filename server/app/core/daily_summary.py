import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from litellm import acompletion

from app.models.data import Timeline, DailySummary
from app.core.prompts import get_daily_summary_prompt
from app.core.logger import get_logger
from app.core.timeline_processor import get_gemini_api_key

logger = get_logger(__name__)
MODEL_NAME = "gemini/gemini-flash-latest"

async def generate_daily_summary(db: AsyncSession, target_date: datetime):
    """
    Generates a high-level summary for a specific day based on Timeline entries.
    """
    logger.info(f"Generating daily summary for {target_date.date()}...")

    # 1. Fetch Timeline entries for the day
    # We need to handle timezones carefully. For now, let's assume the target_date is in UTC 
    # and we want 00:00 to 23:59 UTC. 
    # TODO: In the future, this should respect the user's primary timezone.
    
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
    prompt_template = await get_daily_summary_prompt(db)
    
    current_time_str = datetime.now().strftime("%H:%M")
    
    prompt = prompt_template.format(
        date_str=target_date.strftime("%Y-%m-%d"),
        timeline_json=timeline_str,
        current_time=current_time_str
    )
    
    # 4. Call LLM
    try:
        api_key = await get_gemini_api_key(db)
        if not api_key:
             logger.warning("GEMINI_API_KEY not set. Skipping summary generation.")
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
        
        data = json.loads(content)
        
        # 5. Save/Update DailySummary
        # Check if exists
        stmt = select(DailySummary).where(DailySummary.date == start_of_day)
        result = await db.execute(stmt)
        existing_summary = result.scalars().first()
        
        if existing_summary:
            existing_summary.summary_text = data["summary_text"]
            existing_summary.key_activities = data["key_activities"]
            existing_summary.productivity_score = data.get("productivity_score")
            existing_summary.mood = data.get("mood")
            existing_summary.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.add(existing_summary)
        else:
            new_summary = DailySummary(
                date=start_of_day,
                summary_text=data["summary_text"],
                key_activities=data["key_activities"],
                productivity_score=data.get("productivity_score"),
                mood=data.get("mood")
            )
            db.add(new_summary)
            
        await db.commit()
        logger.info(f"Successfully generated summary for {target_date.date()}")
        
    except Exception as e:
        logger.error(f"Error generating daily summary: {e}")
        import traceback
        traceback.print_exc()

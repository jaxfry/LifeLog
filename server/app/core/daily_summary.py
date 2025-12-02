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

    # 1. Determine User Timezone
    # For now, we'll try to find the most recent timezone from the user's logs or sessions
    # Ideally this should be passed in or associated with a user profile
    # Since we are single user, we can query the latest RawLog
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
    
    # Define start_of_day for summary date field (Normalized to Midnight, naive datetime for DB)
    start_of_day = datetime(
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
        # Convert to local time for the prompt
        local_start = to_local_time(entry.start_time, user_timezone)
        local_end = to_local_time(entry.end_time, user_timezone)
        
        timeline_json.append({
            "start": local_start.strftime("%H:%M"),
            "end": local_end.strftime("%H:%M"),
            "activity": entry.activity,
            "notes": entry.notes
        })
    
    timeline_str = json.dumps(timeline_json, indent=2)
    
    # 3. Get Prompt
    prompt_template = await get_daily_summary_prompt(db)
    
    # Get current time in user's timezone
    current_time_local = to_local_time(datetime.now(timezone.utc), user_timezone)
    current_time_str = current_time_local.strftime("%H:%M")
    
    prompt = prompt_template.format(
        date_str=target_date.strftime("%Y-%m-%d"),
        user_timezone=user_timezone,
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

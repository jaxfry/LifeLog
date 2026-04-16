import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from sqlmodel import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.ai_config import completion_with_fallback

from app.models.data import Timeline, DailySummary
from app.core.prompts import get_daily_summary_prompt, get_daily_summary_patch_prompt
from app.core.logger import get_logger

logger = get_logger(__name__)

async def generate_daily_summary_for_logical_date(db: AsyncSession, logical_date: str):
    logger.info(f"Generating/Patching daily summary for {logical_date}...")

    stmt = select(DailySummary).where(DailySummary.logical_date == logical_date)
    result = await db.execute(stmt)
    existing_summary = result.scalars().first()

    # Timeline entries created AFTER the summary was last generated
    if existing_summary:
        statement = select(Timeline).where(
            Timeline.logical_date == logical_date,
            Timeline.created_at > existing_summary.updated_at
        ).order_by(Timeline.start_time)
    else:
        statement = select(Timeline).where(
            Timeline.logical_date == logical_date
        ).order_by(Timeline.start_time)
    
    result = await db.execute(statement)
    entries = result.scalars().all()
    
    if not entries:
        logger.info(f"No new timeline entries found for {logical_date}. Marking as READY.")
        if existing_summary and existing_summary.status != "READY":
            existing_summary.status = "READY"
            db.add(existing_summary)
            await db.commit()
        return

    user_timezone = entries[0].iana_timezone if entries[0].iana_timezone else "UTC"
    from app.core.utils.time import to_local_time
    
    timeline_json = []
    for entry in entries:
        local_start = to_local_time(entry.start_time, user_timezone)
        local_end = to_local_time(entry.end_time, user_timezone)
        
        timeline_json.append({
            "start": local_start.strftime("%H:%M"),
            "end": local_end.strftime("%H:%M"),
            "activity": entry.activity,
            "notes": entry.notes
        })
    
    timeline_str = json.dumps(timeline_json, indent=2)
    
    current_time_local = to_local_time(datetime.now(timezone.utc), user_timezone)
    current_time_str = current_time_local.strftime("%H:%M")

    is_patch = existing_summary and existing_summary.summary_text and existing_summary.summary_text != "Pending Summary..."
    
    if is_patch:
        logger.info(f"Patching existing summary for {logical_date} with {len(entries)} new events.")
        prompt_template = await get_daily_summary_patch_prompt(db)
        prompt = prompt_template.format(
            date_str=logical_date,
            user_timezone=user_timezone,
            current_time=current_time_str,
            existing_summary_text=existing_summary.summary_text,
            existing_key_activities=json.dumps(existing_summary.key_activities),
            timeline_json=timeline_str
        )
    else:
        logger.info(f"Generating full summary for {logical_date} with {len(entries)} events.")
        prompt_template = await get_daily_summary_prompt(db)
        prompt = prompt_template.format(
            date_str=logical_date,
            user_timezone=user_timezone,
            timeline_json=timeline_str,
            current_time=current_time_str
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
        data = json.loads(content)
        
        if existing_summary:
            existing_summary.summary_text = data["summary_text"]
            existing_summary.key_activities = data["key_activities"]
            existing_summary.productivity_score = data.get("productivity_score")
            existing_summary.mood = data.get("mood")
            existing_summary.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            existing_summary.status = "READY"
            db.add(existing_summary)
        else:
            target_date_local = datetime.strptime(logical_date, "%Y-%m-%d")
            new_summary = DailySummary(
                date=target_date_local,
                logical_date=logical_date,
                summary_text=data["summary_text"],
                key_activities=data["key_activities"],
                productivity_score=data.get("productivity_score"),
                mood=data.get("mood"),
                status="READY",
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            db.add(new_summary)
            
        await db.commit()
    except Exception as e:
        logger.error(f"Error generating daily summary: {e}")

async def generate_daily_summary(db: AsyncSession, target_date: datetime):
    # Try to grab a logical date from the target date naive
    from app.core.utils.time import get_logical_date, get_timezone_obj

    # Just fall back to making logical date from string
    logical_date_str = target_date.strftime("%Y-%m-%d")
    await generate_daily_summary_for_logical_date(db, logical_date_str)

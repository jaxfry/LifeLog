import json
import os
import logging
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from litellm import acompletion

from app.models.data import Event, Timeline, Session, SessionStatus
from app.core.prompts import get_system_prompt

logger = logging.getLogger(__name__)

# Configuration
MODEL_NAME = "gemini/gemini-flash-latest"
MAX_RETRIES = 3

async def process_pending_sessions(db: AsyncSession):
    """
    Fetches pending sessions, generates timeline entries using LLM, and saves them.
    """
    logger.info("Checking for pending sessions...")
    
    # 1. Fetch pending sessions
    statement = select(Session).where(Session.status == SessionStatus.PENDING)
    result = await db.execute(statement)
    sessions = result.scalars().all()
    
    if not sessions:
        logger.info("No pending sessions found.")
        return

    logger.info(f"Found {len(sessions)} pending sessions.")

    for session in sessions:
        await process_session(db, session)

async def process_session(db: AsyncSession, session: Session):
    logger.info(f"Processing session {session.id}...")
    
    # Check retry count
    if session.retry_count >= MAX_RETRIES:
        logger.warning(f"Session {session.id} exceeded max retries. Marking as FAILED.")
        session.status = SessionStatus.FAILED
        db.add(session)
        await db.commit()
        return

    # 1. Fetch events for the session
    stmt = select(Event).where(Event.session_id == session.id).order_by(Event.created_at)
    result = await db.execute(stmt)
    events = result.scalars().all()
    
    if not events:
        logger.info(f"Session {session.id} has no events. Marking as processed.")
        session.status = SessionStatus.PROCESSED
        db.add(session)
        await db.commit()
        return

    # 2. Prepare Event Data (JSON)
    events_data = []
    for event in events:
        # Convert to local time
        utc_dt = event.created_at.replace(tzinfo=timezone.utc)
        local_time_iso = utc_dt.isoformat()
        
        if event.timezone and event.timezone != "UTC":
            try:
                # Parse offset e.g. "-0500"
                dummy = datetime.strptime(f"20000101120000{event.timezone}", "%Y%m%d%H%M%S%z")
                local_dt = utc_dt.astimezone(dummy.tzinfo)
                local_time_iso = local_dt.isoformat()
            except ValueError as e:
                logger.warning(f"Failed to parse timezone {event.timezone} for event {event.id}: {e}")

        evt_dict = {
            "time": local_time_iso,
            "type": event.type,
            "data": event.data
        }
        events_data.append(evt_dict)
        
    events_json = json.dumps(events_data, indent=2)
    
    # 3. Prepare Prompt
    schema_description = """
    {
        "start": "ISO8601 String (Local Time with Offset)",
        "end": "ISO8601 String (Local Time with Offset)",
        "activity": "String",
        "notes": "String"
    }
    """
    
    # Determine session timezone from the first event
    session_timezone_str = "UTC"
    if events and events[0].timezone:
        session_timezone_str = events[0].timezone

    # Calculate day_iso in local time
    session_start_utc = session.start_time.replace(tzinfo=timezone.utc)
    day_iso = session_start_utc.date().isoformat() # Default to UTC

    if session_timezone_str != "UTC":
        try:
             # Parse offset e.g. "-0500"
            dummy = datetime.strptime(f"20000101120000{session_timezone_str}", "%Y%m%d%H%M%S%z")
            session_start_local = session_start_utc.astimezone(dummy.tzinfo)
            day_iso = session_start_local.date().isoformat()
        except ValueError as e:
            logger.warning(f"Failed to parse session timezone {session_timezone_str}: {e}")
    
    # Fetch prompt from DB
    system_prompt_template = await get_system_prompt(db)
    
    prompt = system_prompt_template.format(
        day_iso=day_iso,
        schema_description=schema_description,
        events_json=events_json
    )
    
    # 4. Call LLM
    try:
        # Ensure API key is set
        if not os.environ.get("GEMINI_API_KEY"):
             logger.error("GEMINI_API_KEY not set. Skipping session processing.")
             return

        response = await acompletion(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content
        
        # Clean up code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
            
        content = content.strip()
        
        timeline_data = json.loads(content)
        
        if not isinstance(timeline_data, list):
            logger.error(f"LLM did not return a list for session {session.id}.")
            raise ValueError("Invalid JSON format from LLM")

        # 5. Save to Database
        for entry in timeline_data:
            # Parse timestamps
            # Handle Z or +00:00
            try:
                start_dt = datetime.fromisoformat(entry["start"])
                end_dt = datetime.fromisoformat(entry["end"])
                
                tz_str = "UTC"
                if start_dt.tzinfo:
                    tz_str = start_dt.strftime('%z')
                
                # Convert to UTC for storage
                start_utc = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
                end_utc = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
                
                timeline_entry = Timeline(
                    session_id=session.id,
                    start_time=start_utc,
                    end_time=end_utc,
                    activity=entry["activity"],
                    notes=entry.get("notes"),
                    timezone=tz_str
                )
                db.add(timeline_entry)
            except Exception as e:
                logger.warning(f"Error parsing timeline entry for session {session.id}: {e}")
                continue
            
        # Update session status
        session.status = SessionStatus.PROCESSED
        db.add(session)
        await db.commit()
        logger.info(f"Successfully processed session {session.id} with {len(timeline_data)} timeline entries.")
        
    except Exception as e:
        logger.error(f"Error processing session {session.id}: {e}", exc_info=True)
        # Increment retry count
        session.retry_count += 1
        db.add(session)
        await db.commit()
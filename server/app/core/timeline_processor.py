import json
import os
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlmodel import select, col, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.ai_config import completion_with_fallback

from app.models.data import Event, Timeline, Session, SessionStatus
from app.models.files import FileAttachment
from app.models.config import SystemConfig
from app.core.prompts import get_system_prompt
from app.core.logger import get_logger
from app.core.vector_service import generate_embedding, get_embedding_model_info
from app.core.utils.time import to_local_time


# Configuration
logger = get_logger(__name__)
MAX_RETRIES = 3

async def get_gemini_api_key(db: AsyncSession) -> Optional[str]:
    """
    Fetches the Gemini API key from the database or environment variables.
    """
    # 1. Try DB
    config = await db.get(SystemConfig, "GEMINI_API_KEY")
    if config and config.value:
        return config.value
    
    # 2. Fallback to Env
    return os.environ.get("GEMINI_API_KEY")

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
    stmt = select(Event).where(Event.session_id == session.id, Event.is_superseded == False).order_by(Event.created_at)
    result = await db.execute(stmt)
    events = result.scalars().all()
    
    if not events:
        logger.info(f"Session {session.id} has no events. Marking as processed.")
        session.status = SessionStatus.PROCESSED
        db.add(session)
        await db.commit()
        return

    # 1.5 Fetch linked files (explicitly linked to events OR created during the session)
    event_ids = [e.id for e in events]
    
    # We want files that are:
    # 1. Linked to one of the events in this session
    # 2. OR (Not linked to any event AND created within session time range)
    
    stmt_files = select(FileAttachment).where(
        or_(
            col(FileAttachment.event_id).in_(event_ids),
            and_(
                FileAttachment.event_id.is_(None),
                FileAttachment.created_at >= session.start_time,
                FileAttachment.created_at <= session.end_time
            )
        )
    )
    
    result_files = await db.execute(stmt_files)
    files = result_files.scalars().all()
    
    # Map files to event_id (or "session" if unlinked)
    files_by_event = {}
    session_files = []
    
    for f in files:
        if f.event_id and f.event_id in event_ids:
            if f.event_id not in files_by_event:
                files_by_event[f.event_id] = []
            files_by_event[f.event_id].append(f)
        else:
            # Unlinked file in this time range
            session_files.append(f)

    # 2. Prepare Event Data (JSON)
    events_data = []
    for event in events:
        # Convert to local time
        utc_dt = event.created_at.replace(tzinfo=timezone.utc)
        local_dt = to_local_time(utc_dt, event.timezone)
        local_time_iso = local_dt.isoformat()

        evt_dict = {
            "time": local_time_iso,
            "type": event.type,
            "data": event.data
        }
        
        # Attach file info if present
        if event.id in files_by_event:
            evt_dict["files"] = []
            for f in files_by_event[event.id]:
                file_info = {
                    "filename": f.filename,
                    "category": f.category,
                    "description": f.description,
                    "summary": f.ai_metadata.get("summary") if f.ai_metadata else None,
                    "ocr_text": f.ai_metadata.get("ocr_text")[:200] + "..." if f.ai_metadata and f.ai_metadata.get("ocr_text") else None
                }
                evt_dict["files"].append(file_info)

        events_data.append(evt_dict)
    
    # Add a "Session Files" event if there are unlinked files
    if session_files:
        # We create a synthetic event for these files so the LLM sees them
        # We'll use the session start time or the file's time
        for f in session_files:
            utc_dt = f.created_at.replace(tzinfo=timezone.utc)
            local_dt = to_local_time(utc_dt, session.timezone)
            
            file_evt = {
                "time": local_dt.isoformat(),
                "type": "file_upload",
                "data": {
                    "filename": f.filename,
                    "category": f.category,
                    "description": f.description,
                    "summary": f.ai_metadata.get("summary") if f.ai_metadata else None,
                    "ocr_text": f.ai_metadata.get("ocr_text")[:200] + "..." if f.ai_metadata and f.ai_metadata.get("ocr_text") else None
                }
            }
            events_data.append(file_evt)
            
        # Re-sort events by time because we added new ones
        events_data.sort(key=lambda x: x["time"])
        
    events_json = json.dumps(events_data, indent=2)
    
    # 3. Prepare Prompt
    schema_description = """
    {
        "start": "ISO8601 String (Local Time with Offset)",
        "end": "ISO8601 String (Local Time with Offset)",
        "activity": "String",
        "notes": "String",
        "category": "String (e.g. Work, Personal, Health, Social, Travel, Chores)",
        "tags": ["String"],
        "entities": {"person": ["String"], "place": ["String"], "item": ["String"]}
    }
    """
    
    # Determine session timezone from the first event
    session_timezone_str = "UTC"
    if events and events[0].timezone:
        session_timezone_str = events[0].timezone
        
    # Update session timezone
    session.timezone = session_timezone_str

    # Calculate day_iso in local time
    session_start_utc = session.start_time.replace(tzinfo=timezone.utc)
    session_start_local = to_local_time(session_start_utc, session_timezone_str)
    day_iso = session_start_local.date().isoformat()
    
    # Fetch prompt from DB
    system_prompt_template = await get_system_prompt(db)
    
    prompt = system_prompt_template.format(
        day_iso=day_iso,
        schema_description=schema_description,
        events_json=events_json
    )
    
    # 4. Call LLM
    try:
        response = await completion_with_fallback(
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
                
                # Generate embedding
                embedding_text = f"Activity: {entry['activity']}. Notes: {entry.get('notes', '')}. Category: {entry.get('category', '')}. Tags: {', '.join(entry.get('tags', []))}."
                embedding_vector = await generate_embedding(embedding_text)
                if not embedding_vector:
                    embedding_vector = None
                
                model_info = get_embedding_model_info()

                timeline_entry = Timeline(
                    session_id=session.id,
                    start_time=start_utc,
                    end_time=end_utc,
                    activity=entry["activity"],
                    notes=entry.get("notes"),
                    timezone=tz_str,
                    iana_timezone=session.iana_timezone,
                    logical_date=session.logical_date,
                    category=entry.get("category"),
                    tags=entry.get("tags", []),
                    entities=entry.get("entities", {}),
                    embedding=embedding_vector,
                    embedding_model=model_info["model"],
                    embedding_version=model_info["version"]
                )
                db.add(timeline_entry)
            except Exception as e:
                logger.error(f"Error parsing timeline entry: {e}")
                continue
            
        # Update session status
        session.status = SessionStatus.PROCESSED
        db.add(session)
        
        # Mark DailySummary and DailyChapter as DIRTY for this logical_date
        from app.models.data import DailyChapter, DailySummary
        
        # Chapter
        stmt_chap = select(DailyChapter).where(DailyChapter.logical_date == session.logical_date)
        chapters = (await db.execute(stmt_chap)).scalars().all()
        if chapters:
            for chap in chapters:
                chap.processing_status = "DIRTY"
                chap.last_touched_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.add(chap)
        else:
            # Create a placeholder dummy chapter to hold the dirty state
            dummy_chap = DailyChapter(
                date=session.start_time, # Legacy Date
                logical_date=session.logical_date,
                start_time=session.start_time,
                end_time=session.end_time,
                title="Pending Chapters",
                processing_status="DIRTY",
                last_touched_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            db.add(dummy_chap)

        # Summary
        stmt_sum = select(DailySummary).where(DailySummary.logical_date == session.logical_date)
        summary_obj = (await db.execute(stmt_sum)).scalars().first()
        if summary_obj:
            summary_obj.status = "DIRTY"
            summary_obj.last_touched_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.add(summary_obj)
        else:
            dummy_sum = DailySummary(
                date=datetime.strptime(session.logical_date, "%Y-%m-%d"), # Legacy mapped to logical_date to prevent PK collisions
                logical_date=session.logical_date,
                summary_text="Pending Summary...",
                key_activities=[],
                status="DIRTY",
                last_touched_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            db.add(dummy_sum)

        await db.commit()
        logger.info(f"Successfully processed session {session.id} with {len(timeline_data)} timeline entries.")
        
    except Exception as e:
        logger.error(f"Error processing session {session.id}: {e}")
        # Increment retry count
        session.retry_count += 1
        db.add(session)
        await db.commit()
        import traceback
        traceback.print_exc()
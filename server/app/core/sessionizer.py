import json
from typing import List
from datetime import datetime, timedelta, timezone
import tiktoken
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.data import Event, Session, SessionStatus

# Configuration
TIME_GAP_THRESHOLD = timedelta(minutes=15)
MAX_SESSION_TOKENS = 12000
TOKEN_ENCODING = "cl100k_base"

async def run_sessionizer(db: AsyncSession):
    """
    Groups unassigned events into sessions based on time gaps and token limits.
    """
    # 1. Fetch unassigned events
    statement = select(Event).where(Event.session_id == None, Event.is_superseded == False)
    result = await db.execute(statement)
    events = result.scalars().all()
    
    if not events:
        return

    # 2. Sort by timestamp
    def get_event_time(event: Event) -> datetime:
        ts_str = event.data.get("timestamp")
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                pass
        return event.created_at

    sorted_events = sorted(events, key=get_event_time)
    
    # Initialize tokenizer
    try:
        encoder = tiktoken.get_encoding(TOKEN_ENCODING)
    except Exception:
        encoder = tiktoken.get_encoding("cl100k_base")

    # 3. Group into sessions
    current_session_events: List[Event] = []
    current_token_count = 0
    last_event_end_time = None
    
    for event in sorted_events:
        event_start = get_event_time(event)
        
        # Calculate duration to find end time
        duration = event.data.get("duration", 0)
        if isinstance(duration, (int, float)):
            event_end = event_start + timedelta(seconds=duration)
        else:
            event_end = event_start

        # Calculate tokens for this event
        event_json = json.dumps(event.data)
        event_tokens = len(encoder.encode(event_json))
        
        should_break = False
        
        # Check Time Gap
        if last_event_end_time:
            gap = event_start - last_event_end_time
            if gap > TIME_GAP_THRESHOLD:
                should_break = True
                
        # Check Token Limit
        if current_token_count + event_tokens > MAX_SESSION_TOKENS:
            should_break = True
            
        if should_break and current_session_events:
            await create_session(db, current_session_events)
            current_session_events = []
            current_token_count = 0
            
        current_session_events.append(event)
        current_token_count += event_tokens
        last_event_end_time = event_end
            
    # Close final session if any events remain
    if current_session_events:
        await create_session(db, current_session_events)

async def create_session(db: AsyncSession, events: List[Event]):
    if not events:
        return

    # Calculate session bounds
    def get_event_time(event: Event) -> datetime:
        ts_str = event.data.get("timestamp")
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                return dt.astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                pass
        return event.created_at

    start_times = []
    end_times = []
    
    for e in events:
        start = get_event_time(e)
        duration = e.data.get("duration", 0)
        if isinstance(duration, (int, float)):
            end = start + timedelta(seconds=duration)
        else:
            end = start
        
        start_times.append(start)
        end_times.append(end)
        
    session_start = min(start_times)
    session_end = max(end_times)
    
    # Create Session
    session = Session(
        start_time=session_start,
        end_time=session_end,
        status=SessionStatus.PENDING
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    
    # Update Events
    for e in events:
        e.session_id = session.id
        db.add(e)
        
    await db.commit()


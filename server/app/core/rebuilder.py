from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from uuid import UUID

from app.models.data import Event, Session, Timeline, SessionStatus
from app.core.processing import process_log
from app.core.sessionizer import run_sessionizer
from app.core.timeline_processor import process_pending_sessions, process_session
from app.core.logger import get_logger

logger = get_logger(__name__)

async def trigger_rebuild(session: AsyncSession, source_log_id: str):
    """
    Triggers a cascading rebuild starting from a specific log or event.
    1. Identify affected L2 events.
    2. Mark old events as superseded.
    3. Generate new events.
    4. Invalidate L3 sessions.
    """
    logger.info(f"Triggering rebuild for source_log_id: {source_log_id}")
    
    # Ensure UUID
    if isinstance(source_log_id, str):
        try:
            source_log_id = UUID(source_log_id)
        except ValueError:
            logger.error(f"Invalid UUID string: {source_log_id}")
            return

    # 1. Identify affected L2 events (that are not already superseded)
    stmt = select(Event).where(Event.source_log_id == source_log_id, Event.is_superseded == False)
    result = await session.execute(stmt)
    old_events = result.scalars().all()
    
    if not old_events:
        logger.info(f"No active events found for log {source_log_id}. Proceeding to generate new events.")
    
    affected_session_ids = set()
    for event in old_events:
        if event.session_id:
            affected_session_ids.add(event.session_id)
        # 2. Mark old events as superseded
        event.is_superseded = True
        session.add(event)
    
    # Commit superseded status before generating new events
    await session.commit()

    # 3. Generate new events
    # process_log commits internally
    try:
        await process_log(session, source_log_id)
    except Exception as e:
        logger.error(f"Failed to process log {source_log_id}: {e}")
        # We might want to un-supersede events here, but for now let's just log it.
        return
    
    # 4. Invalidate L3 sessions (Dissolve Strategy)
    if affected_session_ids:
        logger.info(f"Dissolving {len(affected_session_ids)} affected sessions.")
        
        # Detach all events from these sessions (both valid and superseded)
        # Valid events will be re-sessionized. Superseded events will be ignored.
        stmt = select(Event).where(Event.session_id.in_(affected_session_ids))
        result = await session.execute(stmt)
        all_session_events = result.scalars().all()
        
        for event in all_session_events:
            event.session_id = None
            session.add(event)
            
        # Delete Timeline entries for these sessions
        stmt = select(Timeline).where(Timeline.session_id.in_(affected_session_ids))
        result = await session.execute(stmt)
        timelines = result.scalars().all()
        for t in timelines:
            await session.delete(t)
            
        # Delete the Sessions themselves
        stmt = select(Session).where(Session.id.in_(affected_session_ids))
        result = await session.execute(stmt)
        sessions_to_delete = result.scalars().all()
        for s in sessions_to_delete:
            await session.delete(s)
            
        await session.commit()
        
    # 5. Re-run sessionizer
    # This will pick up the new events AND the orphaned events
    logger.info("Running sessionizer after rebuild.")
    await run_sessionizer(session)
    # We do NOT run process_pending_sessions here. The scheduler will pick it up.

async def process_dirty_sessions(session: AsyncSession):
    """
    Finds sessions marked as 'DIRTY' and regenerates their timeline entries.
    """
    logger.info("Checking for dirty sessions...")
    
    # 1. Fetch dirty sessions
    stmt = select(Session).where(Session.status == SessionStatus.DIRTY)
    result = await session.execute(stmt)
    dirty_sessions = result.scalars().all()
    
    if not dirty_sessions:
        logger.info("No dirty sessions found.")
        return
        
    logger.info(f"Found {len(dirty_sessions)} dirty sessions.")
    
    for s in dirty_sessions:
        logger.info(f"Rebuilding session {s.id}...")
        
        # 2. Delete existing timeline entries
        stmt = select(Timeline).where(Timeline.session_id == s.id)
        result = await session.execute(stmt)
        timelines = result.scalars().all()
        
        for t in timelines:
            await session.delete(t)
            
        # 3. Re-process session
        # process_session will generate new timeline entries and set status to PROCESSED
        # We need to reset status to PENDING temporarily? 
        # process_session doesn't check status, it just processes.
        # But it sets status to PROCESSED at the end.
        
        # We should probably commit the deletion first
        await session.commit()
        
        await process_session(session, s)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from uuid import UUID, uuid4
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import asyncio

from app.models.data import Event, Session, Timeline, SessionStatus, DailyChapter
from app.core.processing import process_log
from app.core.sessionizer import run_sessionizer
from app.core.timeline_processor import process_pending_sessions, process_session, get_gemini_api_key
from app.core.chapter_summarizer import generate_daily_chapters
from app.core.vector_service import generate_embedding, get_embedding_model_info, EMBEDDING_MODEL, EMBEDDING_VERSION
from app.core.processing_lock import get_processing_lock
from app.core.logger import get_logger

logger = get_logger(__name__)

# Circuit breaker configuration
MAX_CONSECUTIVE_FAILURES = 5
FAILURE_RESET_TIME = 300  # Reset failure count after 5 minutes

class CircuitBreaker:
    """Prevents hammering failed APIs."""
    def __init__(self):
        self.failure_count = 0
        self.last_failure_time = None
        self.is_open = False
    
    def record_success(self):
        self.failure_count = 0
        self.is_open = False
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= MAX_CONSECUTIVE_FAILURES:
            self.is_open = True
            logger.error(f"Circuit breaker OPEN after {self.failure_count} failures")
    
    def can_proceed(self) -> bool:
        if not self.is_open:
            return True
        
        # Auto-reset after timeout
        if self.last_failure_time and (datetime.now() - self.last_failure_time).seconds > FAILURE_RESET_TIME:
            logger.info("Circuit breaker auto-reset")
            self.failure_count = 0 
            self.is_open = False
            return True
        
        return False

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
        
        # Mark as processing
        s.processing_status = "processing"
        session.add(s)
        await session.commit()
        
        try:
            # 2. Delete existing timeline entries
            stmt = select(Timeline).where(Timeline.session_id == s.id)
            result = await session.execute(stmt)
            timelines = result.scalars().all()
            
            for t in timelines:
                await session.delete(t)
                
            await session.commit()
            
            # 3. Re-process session
            await process_session(session, s)
            
            # Mark as ready
            s.processing_status = "ready"
            session.add(s)
            await session.commit()
            
        except Exception as e:
            logger.error(f"Error processing dirty session {s.id}: {e}")
            s.processing_status = "error"
            session.add(s)
            await session.commit()

async def backfill_embeddings(
    session: AsyncSession,
    batch_size: int = 100,
    timeline_only: bool = False,
    chapters_only: bool = False,
    sleep_delay: float = 1.0, # Default to 1s to respect 100 req/min rate limit
    dry_run: bool = False,
    force: bool = False,
    job_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Backfills embeddings for existing timeline entries and chapters.
    
    Args:
        batch_size: Number of items to process before committing
        timeline_only: Only process timeline entries
        chapters_only: Only process chapters
        sleep_delay: Seconds to sleep between batches (rate limiting)
        dry_run: Calculate what would be done without doing it
        force: Regenerate embeddings even if they exist (for model updates)
        job_id: Unique job identifier for lock management
    """
    if job_id is None:
        job_id = f"backfill_{uuid4()}"
    
    logger.info(f"Starting embedding backfill (job: {job_id}, dry_run: {dry_run}, force: {force})...")
    
    model_info = get_embedding_model_info()
    circuit_breaker = CircuitBreaker()
    
    stats = {
        "job_id": job_id,
        "dry_run": dry_run,
        "timeline_processed": 0,
        "timeline_failed": 0,
        "timeline_skipped": 0,
        "chapters_processed": 0,
        "chapters_failed": 0,
        "chapters_skipped": 0,
        "circuit_breaker_trips": 0
    }
    
    # Get processing lock
    lock = get_processing_lock()
    
    if not dry_run:
        if not lock.acquire(job_id):
            raise Exception(f"Cannot start job - another job is running: {lock.get_current_job()}")
    
    try:
        # Fetch API Key
        api_key = await get_gemini_api_key(session)
        if not api_key and not os.environ.get("GEMINI_API_KEY"):
            logger.warning("No Gemini API Key found. Aborting backfill.")
            return stats

        # Backfill Timeline Embeddings
        if not chapters_only:
            logger.info("Analyzing timeline embeddings...")
            
            if force:
                # Regenerate all embeddings
                stmt = select(Timeline)
            else:
                # Only process missing or outdated model version
                stmt = select(Timeline).where(
                    (Timeline.embedding.is_(None)) | 
                    (Timeline.embedding_model != model_info["model"]) |
                    (Timeline.embedding_version != model_info["version"])
                )
            
            result = await session.execute(stmt)
            timeline_entries = result.scalars().all()
            
            logger.info(f"Found {len(timeline_entries)} timeline entries to process")
            stats["timeline_total"] = len(timeline_entries)
            
            if dry_run:
                stats["timeline_would_process"] = len(timeline_entries)
            else:
                for i, entry in enumerate(timeline_entries):
                    if not circuit_breaker.can_proceed():
                        logger.error("Circuit breaker is OPEN - stopping processing")
                        stats["circuit_breaker_trips"] += 1
                        break
                    
                    try:
                        # Generate embedding text
                        entities_str = " ".join([f"{k}: {v}" for k, v in entry.entities.items()]) if entry.entities else ""
                        embedding_text = f"Activity: {entry.activity}. Notes: {entry.notes or ''}. Category: {entry.category or ''}. Tags: {', '.join(entry.tags or [])}. Entities: {entities_str}."
                        embedding_vector = await generate_embedding(embedding_text, api_key=api_key)
                        
                        if embedding_vector:
                            entry.embedding = embedding_vector
                            entry.embedding_model = model_info["model"]
                            entry.embedding_version = model_info["version"]
                            session.add(entry)
                            stats["timeline_processed"] += 1
                            circuit_breaker.record_success()
                        else:
                            stats["timeline_failed"] += 1
                            circuit_breaker.record_failure()
                        
                        # Commit in batches
                        if (i + 1) % batch_size == 0:
                            await session.commit()
                            logger.info(f"Timeline: Committed batch at {i + 1}/{len(timeline_entries)}")
                            
                            # Update progress
                            lock.update_progress({
                                "phase": "timeline",
                                "processed": str(i + 1),
                                "total": str(len(timeline_entries)),
                                "percentage": str(round((i + 1) / len(timeline_entries) * 100, 1))
                            })
                            
                            # Rate limiting
                            if sleep_delay > 0:
                                await asyncio.sleep(sleep_delay)
                            
                            # Extend lock for long jobs
                            lock.extend_lock(job_id)
                            
                    except Exception as e:
                        logger.error(f"Error generating embedding for timeline {entry.id}: {e}")
                        stats["timeline_failed"] += 1
                        circuit_breaker.record_failure()
                    
                    # Rate limit per request as well, not just per batch
                    if sleep_delay > 0:
                        await asyncio.sleep(sleep_delay)
                
                # Commit remaining
                await session.commit()
                logger.info(f"Timeline backfill complete. Processed: {stats['timeline_processed']}, Failed: {stats['timeline_failed']}")
        
        # Backfill Chapter Embeddings
        if not timeline_only:
            logger.info("Analyzing chapter embeddings...")
            
            if force:
                stmt = select(DailyChapter)
            else:
                stmt = select(DailyChapter).where(
                    (DailyChapter.embedding.is_(None)) |
                    (DailyChapter.embedding_model != model_info["model"]) |
                    (DailyChapter.embedding_version != model_info["version"])
                )
            
            result = await session.execute(stmt)
            chapters = result.scalars().all()
            
            logger.info(f"Found {len(chapters)} chapters to process")
            stats["chapters_total"] = len(chapters)
            
            if dry_run:
                stats["chapters_would_process"] = len(chapters)
            else:
                for i, chapter in enumerate(chapters):
                    if not circuit_breaker.can_proceed():
                        logger.error("Circuit breaker is OPEN - stopping processing")
                        stats["circuit_breaker_trips"] += 1
                        break
                    
                    try:
                        # Mark as processing
                        chapter.processing_status = "processing"
                        session.add(chapter)
                        await session.commit()
                        
                        # Generate embedding text
                        embedding_text = f"Title: {chapter.title}. Summary: {chapter.summary or ''}. Category: {chapter.category or ''}. Tags: {', '.join(chapter.tags or [])}."
                        embedding_vector = await generate_embedding(embedding_text, api_key=api_key)
                        
                        if embedding_vector:
                            chapter.embedding = embedding_vector
                            chapter.embedding_model = model_info["model"]
                            chapter.embedding_version = model_info["version"]
                            chapter.processing_status = "ready"
                            session.add(chapter)
                            stats["chapters_processed"] += 1
                            circuit_breaker.record_success()
                        else:
                            chapter.processing_status = "error"
                            session.add(chapter)
                            stats["chapters_failed"] += 1
                            circuit_breaker.record_failure()
                        
                        # Commit in batches
                        if (i + 1) % batch_size == 0:
                            await session.commit()
                            logger.info(f"Chapters: Committed batch at {i + 1}/{len(chapters)}")
                            
                            # Update progress
                            lock.update_progress({
                                "phase": "chapters",
                                "processed": str(i + 1),
                                "total": str(len(chapters)),
                                "percentage": str(round((i + 1) / len(chapters) * 100, 1))
                            })
                            
                            if sleep_delay > 0:
                                await asyncio.sleep(sleep_delay)
                            
                            lock.extend_lock(job_id)
                            
                    except Exception as e:
                        logger.error(f"Error generating embedding for chapter {chapter.id}: {e}")
                        chapter.processing_status = "error"
                        session.add(chapter)
                        stats["chapters_failed"] += 1
                        circuit_breaker.record_failure()
                    
                    # Rate limit per request
                    if sleep_delay > 0:
                        await asyncio.sleep(sleep_delay)
                
                # Commit remaining
                await session.commit()
                logger.info(f"Chapter backfill complete. Processed: {stats['chapters_processed']}, Failed: {stats['chapters_failed']}")
    
    finally:
        if not dry_run:
            lock.release(job_id)
    
    return stats

async def reprocess_date_range(
    session: AsyncSession,
    start_date: datetime,
    end_date: datetime,
    regenerate_chapters: bool = True,
    dry_run: bool = False,
    job_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Reprocesses all sessions and chapters within a date range.
    """
    if job_id is None:
        job_id = f"reprocess_{uuid4()}"
    
    logger.info(f"Reprocessing date range {start_date.date()} to {end_date.date()} (job: {job_id}, dry_run: {dry_run})")
    
    stats = {
        "job_id": job_id,
        "dry_run": dry_run,
        "sessions_marked_dirty": 0,
        "chapters_regenerated": 0,
        "errors": []
    }
    
    # Get lock
    lock = get_processing_lock()
    if not dry_run:
        if not lock.acquire(job_id):
            raise Exception(f"Cannot start job - another job is running: {lock.get_current_job()}")
    
    try:
        # Mark sessions in range as DIRTY
        stmt = select(Session).where(
            Session.start_time >= start_date,
            Session.start_time <= end_date
        )
        result = await session.execute(stmt)
        sessions = result.scalars().all()
        
        logger.info(f"Found {len(sessions)} sessions in date range")
        stats["sessions_found"] = len(sessions)
        
        if dry_run:
            stats["sessions_would_mark_dirty"] = len(sessions)
        else:
            for s in sessions:
                s.status = SessionStatus.DIRTY
                s.processing_status = "pending"
                session.add(s)
                stats["sessions_marked_dirty"] += 1
            
            await session.commit()
            logger.info(f"Marked {stats['sessions_marked_dirty']} sessions as DIRTY")
            
            # Process dirty sessions
            await process_dirty_sessions(session)
        
        # Regenerate chapters if requested
        if regenerate_chapters:
            current_date = start_date
            days_to_process = (end_date - start_date).days + 1
            
            if dry_run:
                stats["chapters_would_regenerate"] = days_to_process
            else:
                logger.info(f"Regenerating chapters for {days_to_process} days")
                day_num = 0
                
                while current_date <= end_date:
                    try:
                        await generate_daily_chapters(session, current_date)
                        stats["chapters_regenerated"] += 1
                        
                        day_num += 1
                        lock.update_progress({
                            "phase": "chapters",
                            "processed": str(day_num),
                            "total": str(days_to_process),
                            "percentage": str(round(day_num / days_to_process * 100, 1))
                        })
                        
                    except Exception as e:
                        error_msg = f"Failed to regenerate chapters for {current_date.date()}: {e}"
                        logger.error(error_msg)
                        stats["errors"].append(error_msg)
                    
                    current_date += timedelta(days=1)
                    lock.extend_lock(job_id)
    
    finally:
        if not dry_run:
            lock.release(job_id)
    
    return stats

async def get_reprocessing_status(session: AsyncSession) -> Dict[str, Any]:
    """
    Returns statistics about data that needs reprocessing.
    """
    model_info = get_embedding_model_info()
    
    # Count timeline entries without embeddings or outdated model
    stmt = select(Timeline).where(
        (Timeline.embedding.is_(None)) |
        (Timeline.embedding_model != model_info["model"]) |
        (Timeline.embedding_version != model_info["version"])
    )
    result = await session.execute(stmt)
    timeline_missing = len(result.scalars().all())
    
    # Count chapters without embeddings or outdated model
    stmt = select(DailyChapter).where(
        (DailyChapter.embedding.is_(None)) |
        (DailyChapter.embedding_model != model_info["model"]) |
        (DailyChapter.embedding_version != model_info["version"])
    )
    result = await session.execute(stmt)
    chapters_missing = len(result.scalars().all())
    
    # Count dirty sessions
    stmt = select(Session).where(Session.status == SessionStatus.DIRTY)
    result = await session.execute(stmt)
    dirty_sessions = len(result.scalars().all())
    
    # Count pending sessions
    stmt = select(Session).where(Session.status == SessionStatus.PENDING)
    result = await session.execute(stmt)
    pending_sessions = len(result.scalars().all())
    
    # Count processing items
    stmt = select(Session).where(Session.processing_status == "processing")
    result = await session.execute(stmt)
    sessions_processing = len(result.scalars().all())
    
    stmt = select(DailyChapter).where(DailyChapter.processing_status == "processing")
    result = await session.execute(stmt)
    chapters_processing = len(result.scalars().all())
    
    # Count total timeline and chapters
    stmt = select(Timeline)
    result = await session.execute(stmt)
    total_timeline = len(result.scalars().all())
    
    stmt = select(DailyChapter)
    result = await session.execute(stmt)
    total_chapters = len(result.scalars().all())
    
    # Check if a job is running
    lock = get_processing_lock()
    is_processing = lock.is_locked()
    current_job = lock.get_current_job()
    progress = lock.get_progress()
    
    return {
        "embedding_model": model_info,
        "timeline": {
            "total": total_timeline,
            "missing_or_outdated_embeddings": timeline_missing,
            "percentage_complete": round((total_timeline - timeline_missing) / total_timeline * 100, 2) if total_timeline > 0 else 100
        },
        "chapters": {
            "total": total_chapters,
            "missing_or_outdated_embeddings": chapters_missing,
            "processing": chapters_processing,
            "percentage_complete": round((total_chapters - chapters_missing) / total_chapters * 100, 2) if total_chapters > 0 else 100
        },
        "sessions": {
            "dirty": dirty_sessions,
            "pending": pending_sessions,
            "processing": sessions_processing
        },
        "job_status": {
            "is_running": is_processing,
            "current_job_id": current_job,
            "progress": progress
        }
    }

"""
Background Task Scheduler for LifeLog

Provides scheduled tasks like daily timeline generation.
For production, consider using Celery, APScheduler, or similar.
"""

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class ScheduledTaskRunner:
    """
    Simple scheduler for background tasks.
    
    In production, replace with a proper task queue (Celery, RQ, etc.).
    """
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the background task scheduler."""
        if self._running:
            logger.warning("Scheduler already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_scheduler())
        logger.info("Background task scheduler started")
    
    async def stop(self):
        """Stop the background task scheduler."""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Background task scheduler stopped")
    
    async def _run_scheduler(self):
        """Main scheduler loop."""
        while self._running:
            try:
                await self._check_and_run_tasks()
                # Check every 60 seconds
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Scheduler error: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    async def _check_and_run_tasks(self):
        """Check if any scheduled tasks should run."""
        now = datetime.now(timezone.utc)
        
        # Daily timeline generation at 2 AM UTC
        if await self._should_run_daily_task("timeline_generation", now, time(hour=2, minute=0)):
            logger.info("Running scheduled daily timeline generation")
            await self._run_daily_timeline_generation()
    
    async def _should_run_daily_task(
        self,
        task_name: str,
        now: datetime,
        scheduled_time: time
    ) -> bool:
        """
        Check if a daily task should run.
        
        Simple implementation: run if we're within 2 minutes of the scheduled time
        and haven't run yet today.
        """
        # Check if we're near the scheduled time
        current_time = now.time()
        scheduled_hour = scheduled_time.hour
        scheduled_minute = scheduled_time.minute
        
        # Within 2-minute window?
        is_time_match = (
            current_time.hour == scheduled_hour and
            abs(current_time.minute - scheduled_minute) <= 1
        )
        
        if not is_time_match:
            return False
        
        # Simple guard: check if we've already run today
        # In production, use a persistent state store
        last_run_key = f"_last_run_{task_name}"
        last_run = getattr(self, last_run_key, None)
        
        if last_run:
            if isinstance(last_run, datetime):
                # Already ran today?
                if last_run.date() == now.date():
                    return False
        
        # Mark as running
        setattr(self, last_run_key, now)
        return True
    
    async def _run_daily_timeline_generation(self):
        """Run daily timeline generation for yesterday."""
        try:
            from ..db import async_session
            from ..core.actors import actor_registry
            
            # Get the timeline-enricher actor
            ActorClass = actor_registry.get_actor_class("timeline-enricher")
            if not ActorClass:
                logger.error("timeline-enricher actor not found in registry")
                return
            
            # Generate timeline for yesterday
            end_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            start_time = end_time - timedelta(days=1)
            
            actor_data = {
                "start_time": start_time,
                "end_time": end_time,
                "force_regenerate": False,
                "budget": {
                    "max_characters": 4000
                }
            }
            
            actor_instance = ActorClass()
            result = await actor_instance.run(actor_data)
            
            logger.info(f"Daily timeline generation completed: {result}")
            
        except Exception as e:
            logger.error(f"Daily timeline generation failed: {e}", exc_info=True)


# Global scheduler instance
_scheduler: Optional[ScheduledTaskRunner] = None


def get_scheduler() -> ScheduledTaskRunner:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = ScheduledTaskRunner()
    return _scheduler


async def start_scheduler():
    """Start the background scheduler."""
    scheduler = get_scheduler()
    await scheduler.start()


async def stop_scheduler():
    """Stop the background scheduler."""
    scheduler = get_scheduler()
    await scheduler.stop()

from sqlalchemy.ext.asyncio import AsyncSession

async def trigger_rebuild(session: AsyncSession, source_log_id: str):
    """
    Triggers a cascading rebuild starting from a specific log or event.
    1. Identify affected L2 events.
    2. Mark old events as superseded.
    3. Generate new events.
    4. Invalidate L3 sessions.
    """

async def process_dirty_sessions(session: AsyncSession):
    """
    Finds sessions marked as 'needs_rebuild' and regenerates their timeline entries.
    """

"""
Timeline Service

Provides database operations for timeline events.
"""

from typing import List, Optional
from datetime import datetime
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ..models import Event, EventType


class TimelineService:
    """Service for timeline operations"""
    
    @staticmethod
    async def get_timeline_events(
        session: AsyncSession,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        skip: int = 0
    ) -> List[Event]:
        """Get timeline events with optional filters"""
        query = select(Event)
        
        if start_time:
            query = query.where(Event.start_time >= start_time)
        if end_time:
            query = query.where(Event.start_time <= end_time)
            
        query = query.order_by(Event.start_time.desc()).offset(skip).limit(limit)
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def get_event_by_id(session: AsyncSession, event_id: int) -> Optional[Event]:
        """Get a specific event by ID"""
        query = select(Event).where(Event.id == event_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_event_type_name(session: AsyncSession, event_type_id: int) -> str:
        """Get event type name by ID"""
        query = select(EventType).where(EventType.id == event_type_id)
        result = await session.execute(query)
        event_type = result.scalar_one_or_none()
        # EventType model does not have a 'name' field; use slug as the identifier
        return event_type.slug if event_type else "unknown"

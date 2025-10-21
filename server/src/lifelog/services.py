"""
Service layer for LifeLog application.

This module implements the service layer to abstract database operations
and remove hardcoded queries from API endpoints, as specified in the architecture.
"""

from typing import List, Optional
from datetime import datetime
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from sqlalchemy.exc import IntegrityError
from datetime import datetime as dt

from . import models


class TimelineService:
    """Service for timeline-related operations"""
    
    @staticmethod
    async def get_timeline_events(
        session: AsyncSession,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        skip: int = 0
    ) -> List[models.Event]:
        """
        Get timeline events, only returning non-superseded events.
        
        This implements the architecture requirement to filter for events
        WHERE superseded_by_event_id IS NULL.
        """
        col_superseded = models.Event.superseded_by_event_id  # type: ignore[attr-defined]
        query = select(models.Event).where(col_superseded.is_(None))  # type: ignore[attr-defined]

        # Apply time filters if provided
        if start_time:
            query = query.where(models.Event.start_time >= start_time)
        if end_time:
            query = query.where(models.Event.start_time <= end_time)

        # Order by start time (most recent first) and apply pagination
        query = query.order_by(models.Event.start_time.desc()).offset(skip).limit(limit)  # type: ignore[attr-defined]

        result = await session.exec(query)
        return list(result.all())
    
    @staticmethod
    async def get_event_by_id(session: AsyncSession, event_id: int) -> Optional[models.Event]:
        """Get a specific event by ID, only if not superseded"""
        col_superseded = models.Event.superseded_by_event_id  # type: ignore[attr-defined]
        query = select(models.Event).where(
            models.Event.id == event_id,
            col_superseded.is_(None)  # type: ignore[attr-defined]
        )
        
        result = await session.exec(query)
        return result.first()
    
    @staticmethod
    async def get_event_type_name(session: AsyncSession, event_type_id: int) -> str:
        """Get event type name by ID"""
        query = select(models.EventType).where(models.EventType.id == event_type_id)
        result = await session.exec(query)
        event_type = result.first()
        return event_type.slug if event_type else "unknown"


class IngestionService:
    """Service for data ingestion operations"""
    
    @staticmethod
    async def find_source_actor(session: AsyncSession, actor_slug: str) -> Optional[models.Actor]:
        """Find a source actor by slug"""
        query = select(models.Actor).where(models.Actor.slug == actor_slug)
        result = await session.exec(query)
        return result.first()
    
    @staticmethod
    async def create_raw_log(
        session: AsyncSession, 
        source_actor_id: int, 
        data: dict,
        device_id: Optional[int] = None
    ) -> models.RawLog:
        """Create a new raw log entry"""
        db_raw_log = models.RawLog(
            source_actor_id=source_actor_id,
            device_id=device_id,
            raw_data=data
        )
        
        session.add(db_raw_log)
        await session.commit()
        await session.refresh(db_raw_log)

        # Update device last_seen if applicable
        if device_id is not None:
            device = await session.get(models.Device, device_id)
            if device:
                device.last_seen = dt.utcnow()
                session.add(device)
                await session.commit()
        return db_raw_log


class ExtensionService:
    """Service for extension management operations"""
    
    @staticmethod
    async def get_extensions_with_actors(session: AsyncSession) -> List[models.Extension]:
        """Get all extensions with their associated actors"""
        from sqlalchemy.orm import selectinload

        query = select(models.Extension).options(selectinload(models.Extension.actors))  # type: ignore[arg-type]
        result = await session.exec(query)
        return list(result.all())
    
    @staticmethod
    async def create_extension_with_actors(
        session: AsyncSession,
        extension_data: dict,
        actors_data: List[dict]
    ) -> models.Extension:
        """Create an extension with its associated actors"""
        # Check for existing extension
        existing_query = select(models.Extension).where(
            models.Extension.slug == extension_data["slug"]
        )
        result = await session.exec(existing_query)
        if result.first():
            raise ValueError(f"Extension with slug '{extension_data['slug']}' already exists")
        
        # Create extension and actors
        db_extension = models.Extension(**extension_data)
        
        for actor_data in actors_data:
            db_actor = models.Actor.model_validate(actor_data)
            db_extension.actors.append(db_actor)
        
        session.add(db_extension)
        await session.flush()
        extension_id = db_extension.id
        await session.commit()
        
        # Fetch with relationships loaded
        from sqlalchemy.orm import selectinload
        final_query = (
            select(models.Extension)
            .where(models.Extension.id == extension_id)
            .options(selectinload(models.Extension.actors))  # type: ignore[arg-type]
        )
        result = await session.exec(final_query)

        return result.one()


class ProcessingService:
    """Service for processing operations"""
    
    @staticmethod
    async def get_raw_log_with_source_actor(
        session: AsyncSession, 
        raw_log_id: int
    ) -> Optional[models.RawLog]:
        """Get a raw log with its source actor relationship loaded"""
        raw_log = await session.get(models.RawLog, raw_log_id)
        if raw_log:
            # Eagerly load the source_actor relationship
            await session.refresh(raw_log, attribute_names=["source_actor"])
        return raw_log


class ProcessingRoutingService:
    """Service to resolve processor actor for a given source actor."""

    @staticmethod
    async def resolve_processor_slug(
        session: AsyncSession,
        source_actor_slug: str,
    ) -> Optional[str]:
        """
        Resolve the processor actor slug for a source actor slug.
        Order of precedence:
         1) DB mapping via ActorRouting
         2) settings.PROCESSING_ROUTING_MAP
        """
        # Try DB mapping first
        stmt_source = select(models.Actor).where(models.Actor.slug == source_actor_slug)
        src = (await session.exec(stmt_source)).one_or_none()
        if src:
            stmt_map = select(models.ActorRouting).where(models.ActorRouting.source_actor_id == src.id)
            route = (await session.exec(stmt_map)).one_or_none()
            if route:
                processor = await session.get(models.Actor, route.processor_actor_id)
                return processor.slug if processor else None

        # Fallback to config map
        from .core.config import settings  # type: ignore
        return settings.PROCESSING_ROUTING_MAP.get(source_actor_slug)
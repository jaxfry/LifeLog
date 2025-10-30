"""
Service layer for LifeLog application.

This module implements the service layer to abstract database operations
and remove hardcoded queries from API endpoints, as specified in the architecture.
"""

import logging
from typing import List, Optional, Tuple
from datetime import datetime, timezone
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from sqlalchemy import func

from . import models
from .auth import hash_api_key
from .core.ai import ai_service
from .constants import ProcessingStatus
from .manifest import ExtensionManifest

logger = logging.getLogger(__name__)


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
                # Use timezone-aware UTC to match TIMESTAMPTZ columns
                device.last_seen = datetime.now(timezone.utc)
                session.add(device)
                await session.commit()
        # Session commits expire objects by default; ensure id remains accessible
        await session.refresh(db_raw_log)
        return db_raw_log


class EventService:
    """Service for event-related operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_events_in_range(
        self, start_time: datetime, end_time: datetime
    ) -> List[models.Event]:
        """Fetch non-superseded events within a given time range."""
        stmt = (
            select(models.Event)
            .where(models.Event.start_time >= start_time)
            .where(models.Event.start_time <= end_time)
            .where(models.Event.superseded_by_event_id.is_(None))  # type: ignore[attr-defined]
            .order_by(models.Event.start_time)  # type: ignore[arg-type]
        )
        result = await self.session.exec(stmt)
        return list(result.all())

    @staticmethod
    async def supersede_prior_events_for_raw_log(
        session: AsyncSession,
        *,
        processor_actor_id: int,
        raw_log_id: int,
        new_event_id: int,
    ) -> list[int]:
        """
        Mark any existing, non-superseded Events created by the same processor for
        the given RawLog as superseded by the new event. Returns list of superseded ids.

        Contract:
        - Inputs: processor_actor_id, raw_log_id, new_event_id (persisted)
        - Output: list of event IDs that were superseded
        - Non-destructive: only updates superseded_by_event_id, never deletes
        """
        from . import models
        from sqlmodel import select

        # Find candidate prior events
        stmt = (
            select(models.Event)
            .join(models.EventRawLogLink, models.EventRawLogLink.event_id == models.Event.id)  # type: ignore[arg-type]
            .where(models.EventRawLogLink.raw_log_id == raw_log_id)
            .where(models.Event.processor_actor_id == processor_actor_id)
            .where(models.Event.superseded_by_event_id.is_(None))  # type: ignore[attr-defined]
            .where(models.Event.id != new_event_id)
        )
        prior_events = list((await session.exec(stmt)).all())
        superseded_ids: list[int] = []
        for ev in prior_events:
            if ev.id is None:
                continue
            ev.superseded_by_event_id = new_event_id
            session.add(ev)
            superseded_ids.append(ev.id)
        if superseded_ids:
            await session.flush()
        return superseded_ids

    @staticmethod
    async def supersede_event_set(
        session: AsyncSession,
        *,
        old_event_ids: list[int],
        new_event_id: int,
    ) -> list[int]:
        """
        Supersede a provided set of old event IDs by a single new event ID.

        Notes:
        - Ignores the new_event_id if it appears in old_event_ids.
        - Only updates events that are not already superseded.
        - Returns the list of event IDs that were updated.
        """
        from . import models
        from sqlmodel import select

        ids = [eid for eid in set(old_event_ids) if eid != new_event_id]
        if not ids:
            return []

        stmt = (
            select(models.Event)
            .where(models.Event.id.in_(ids))  # type: ignore[attr-defined]
            .where(models.Event.superseded_by_event_id.is_(None))  # type: ignore[attr-defined]
        )
        rows = list((await session.exec(stmt)).all())
        updated: list[int] = []
        for ev in rows:
            if ev.id is None:
                continue
            ev.superseded_by_event_id = new_event_id
            session.add(ev)
            updated.append(ev.id)
        if updated:
            await session.flush()
        return updated


class SynthesisService:
    """Service for creating and managing synthesis reports."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_synthesis_report(
        self,
        *,
        actor_id: int,
        start_time: datetime,
        end_time: datetime,
        report_type: str,
        report_data: dict,
        event_ids: List[int],
        ai_usage_log_id: Optional[int] = None,
    ) -> models.SynthesisReport:
        """Creates a new synthesis report and links it to events.

        Alignment note: Per architecture, we must NEVER delete past records.
        We create the new report first, then mark any previous ones as superseded
        by setting superseded_by_report_id.
        """

        # Fetch Event objects for linking
        events = []
        if event_ids:
            event_stmt = select(models.Event).where(models.Event.id.in_(event_ids))  # type: ignore[attr-defined]
            events = list((await self.session.exec(event_stmt)).all())

        report = models.SynthesisReport(
            actor_id=actor_id,
            start_time=start_time,
            end_time=end_time,
            report_type=report_type,
            report_data=report_data,
            ai_usage_log_id=ai_usage_log_id,
            events=events,
        )

        self.session.add(report)
        # Flush to assign an ID without committing the transaction yet
        await self.session.flush()
        await self.session.refresh(report)

        # Supersede any existing reports for the same actor/type/day
        await self._supersede_existing_reports(
            actor_id=actor_id,
            report_type=report_type,
            start_time=start_time,
            new_report_id=report.id,  # type: ignore[arg-type]
        )

        # Commit after supersession updates are applied
        await self.session.commit()
        return report

    async def _supersede_existing_reports(
        self, actor_id: int, report_type: str, start_time: datetime, new_report_id: Optional[int]
    ):
        """Finds and marks existing reports as superseded (non-destructive).

        Any existing reports for the same actor, type, and day that are not
        already superseded will have their superseded_by_report_id set to the
        newly created report's id.
        """
        # If we don't have a new report id for some reason, abort safely
        if new_report_id is None:
            return

        # We define a report as "existing" if it's for the same actor, type, and day.
        report_date = start_time.date()
        day_start = datetime.combine(report_date, datetime.min.time())
        day_end = datetime.combine(report_date, datetime.max.time())

        # Select existing, non-superseded reports in that day window
        stmt = (
            select(models.SynthesisReport)
            .where(models.SynthesisReport.actor_id == actor_id)
            .where(models.SynthesisReport.report_type == report_type)
            .where(models.SynthesisReport.start_time >= day_start)
            .where(models.SynthesisReport.start_time <= day_end)
            .where(models.SynthesisReport.superseded_by_report_id.is_(None))  # type: ignore[attr-defined]
        )
        existing = list((await self.session.exec(stmt)).all())
        if not existing:
            return

        # Mark them as superseded by the newly created report
        for rep in existing:
            rep.superseded_by_report_id = new_report_id
            self.session.add(rep)
        await self.session.flush()


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

    @staticmethod
    async def create_extension_from_manifest(
        session: AsyncSession,
        manifest: ExtensionManifest,
        update_if_exists: bool = False
    ) -> Tuple[models.Extension, bool]:
        """
        Create or update an extension from a manifest.json structure.
        
        Stores the full manifest in extension.config for client synchronization.
        
        Returns: (extension, is_new_version) where is_new_version=True if an upgrade occurred.
        """
        # Check if extension already exists
        existing_stmt = select(models.Extension).where(models.Extension.slug == manifest.slug)
        existing = (await session.exec(existing_stmt)).one_or_none()

        # Store the full manifest for client sync
        manifest_dict = manifest.model_dump()
        full_config = {
            "server_side": manifest_dict.get("server_side"),
            "client_side": manifest_dict.get("client_side"),
            **(manifest.config or {})
        }

        is_upgrade = False
        if existing:
            if not update_if_exists:
                raise ValueError(f"Extension '{manifest.slug}' already exists. Use update_if_exists=True to upgrade.")
            
            # Check if version changed
            if existing.version != manifest.version:
                is_upgrade = True
            
            # Update extension metadata
            existing.name = manifest.name
            existing.version = manifest.version
            existing.config = full_config
            session.add(existing)
            extension = existing
        else:
            # Create new extension
            extension = models.Extension(
                slug=manifest.slug,
                name=manifest.name,
                version=manifest.version,
                is_active=True,
                config=full_config
            )
            session.add(extension)
            await session.flush()

        # Sync actors
        if manifest.server_side and manifest.server_side.actors:
            for actor_def in manifest.server_side.actors:
                # Try to find existing actor
                actor_stmt = (
                    select(models.Actor)
                    .where(models.Actor.extension_id == extension.id)
                    .where(models.Actor.slug == actor_def.slug)
                )
                actor = (await session.exec(actor_stmt)).one_or_none()

                if actor:
                    # Update version if changed
                    if actor.version != actor_def.version:
                        actor.version = actor_def.version
                        actor.actor_type = models.ActorType(actor_def.type)
                        session.add(actor)
                else:
                    # Create new actor
                    new_actor = models.Actor(
                        extension_id=extension.id,  # type: ignore[arg-type]
                        slug=actor_def.slug,
                        actor_type=models.ActorType(actor_def.type),
                        version=actor_def.version
                    )
                    session.add(new_actor)

        # Sync event types
        if manifest.server_side and manifest.server_side.event_types:
            for et_def in manifest.server_side.event_types:
                et_stmt = (
                    select(models.EventType)
                    .where(models.EventType.owner_extension_id == extension.id)
                    .where(models.EventType.slug == et_def.slug)
                )
                et = (await session.exec(et_stmt)).one_or_none()
                if not et:
                    new_et = models.EventType(
                        owner_extension_id=extension.id,  # type: ignore[arg-type]
                        slug=et_def.slug,
                        description=et_def.description
                    )
                    session.add(new_et)

        # Sync prompt templates
        if manifest.server_side and manifest.server_side.prompt_templates:
            for pt_def in manifest.server_side.prompt_templates:
                pt_stmt = (
                    select(models.PromptTemplate)
                    .where(models.PromptTemplate.owner_extension_id == extension.id)
                    .where(models.PromptTemplate.slug == pt_def.slug)
                )
                pt = (await session.exec(pt_stmt)).one_or_none()
                if not pt:
                    new_pt = models.PromptTemplate(
                        owner_extension_id=extension.id,  # type: ignore[arg-type]
                        slug=pt_def.slug,
                        description=pt_def.description,
                        template_text=pt_def.template_text,
                        version=pt_def.version
                    )
                    session.add(new_pt)

        await session.commit()
        await session.refresh(extension)
        
        # Apply managed schemas if defined
        if manifest.server_side and manifest.server_side.managed_schemas:
            from .core.schema_manager import get_schema_manager
            schema_manager = get_schema_manager()
            
            try:
                schema_results = await schema_manager.apply_managed_schemas(
                    session,
                    manifest.slug,
                    manifest.server_side.managed_schemas
                )
                logger.info(f"Applied managed schemas for '{manifest.slug}': {schema_results}")
            except Exception as e:
                logger.error(f"Failed to apply managed schemas for '{manifest.slug}': {e}")
                # Don't fail the extension installation, just log the error
                # The extension can still work without custom tables
        
        return extension, is_upgrade


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

    @staticmethod
    async def find_raw_logs_for_reprocessing(
        session: AsyncSession,
        actor_slug: str,
        current_version: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[int]:
        """
        Find raw_log IDs that were previously processed by an older version of an actor.
        
        Args:
            session: Database session
            actor_slug: Slug of the actor to reprocess for
            current_version: Current version of the actor
            start_date: Optional start date filter (inclusive)
            end_date: Optional end date filter (inclusive)
        
        Returns list of raw_log_ids that should be reprocessed.
        """
        # Find the actor (get latest by ID if multiple match)
        actor_stmt = (
            select(models.Actor)
            .where(models.Actor.slug == actor_slug)
            .order_by(models.Actor.id.desc())  # type: ignore[attr-defined]
            .limit(1)
        )
        result = await session.exec(actor_stmt)
        actor = result.first()
        if not actor or actor.id is None:
            return []

        # Build base query for processing log entries
        log_stmt = (
            select(models.ActorProcessingLog.raw_log_id)
            .where(models.ActorProcessingLog.actor_id == actor.id)
            .where(models.ActorProcessingLog.actor_version_at_processing != current_version)
            .where(models.ActorProcessingLog.status == ProcessingStatus.SUCCESS)
            .where(models.ActorProcessingLog.raw_log_id.isnot(None))  # type: ignore[attr-defined]
        )
        
        # Apply date filters if provided
        if start_date or end_date:
            # Join with raw_logs to filter by ingestion date
            from sqlalchemy import and_
            log_stmt = log_stmt.join(
                models.RawLog,
                models.ActorProcessingLog.raw_log_id == models.RawLog.id,  # type: ignore[arg-type]
                isouter=False
            )
            
            if start_date:
                log_stmt = log_stmt.where(models.RawLog.ingested_at >= start_date)
            if end_date:
                log_stmt = log_stmt.where(models.RawLog.ingested_at <= end_date)
        
        log_stmt = log_stmt.distinct()
        
        result = await session.exec(log_stmt)
        raw_log_ids = [row for row in result.all() if row is not None]
        return raw_log_ids
    
    @staticmethod
    async def estimate_reprocessing_cost(
        session: AsyncSession,
        actor_slug: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> dict:
        """
        Estimate the cost and scope of reprocessing before actually doing it.
        
        Returns:
            {
                "raw_logs_affected": int,
                "estimated_ai_calls": int,
                "estimated_cost_usd": float,
                "estimated_duration_minutes": int,
                "current_version": str,
                "date_range": {"start": str, "end": str} or None
            }
        """
        # Find the actor and get current version (get latest by ID if multiple match)
        actor_stmt = (
            select(models.Actor)
            .where(models.Actor.slug == actor_slug)
            .order_by(models.Actor.id.desc())  # type: ignore[attr-defined]
            .limit(1)
        )
        result = await session.exec(actor_stmt)
        actor = result.first()
        if not actor:
            raise ValueError(f"Actor '{actor_slug}' not found")
        
        current_version = actor.version
        
        # Find raw_logs that would be reprocessed
        raw_log_ids = await ProcessingService.find_raw_logs_for_reprocessing(
            session, actor_slug, current_version, start_date, end_date
        )
        
        # Get historical AI usage for this actor
        avg_cost_stmt = (
            select(func.avg(models.AIUsageLog.cost))
            .where(models.AIUsageLog.actor_id == actor.id)
            .where(models.AIUsageLog.cost.isnot(None))  # type: ignore[attr-defined]
        )
        result = await session.exec(avg_cost_stmt)
        avg_cost_per_call = result.one() or 0.01  # Default to 1 cent if no history
        
        # Estimate processing time (rough heuristic: 100 items per minute)
        estimated_duration = max(1, len(raw_log_ids) // 100)
        
        return {
            "raw_logs_affected": len(raw_log_ids),
            "estimated_ai_calls": len(raw_log_ids),  # Assume 1 AI call per raw_log
            "estimated_cost_usd": round(len(raw_log_ids) * float(avg_cost_per_call), 2),
            "estimated_duration_minutes": estimated_duration,
            "current_version": current_version,
            "date_range": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            } if (start_date or end_date) else None
        }


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


class DeviceService:
    """Service for device management operations"""

    @staticmethod
    def generate_api_key() -> str:
        """Generate a secure random API key for a device"""
        import secrets
        return secrets.token_urlsafe(32)

    @staticmethod
    async def create_device(
        session: AsyncSession,
        name: str,
        device_type: Optional[str] = None,
        client_metadata: Optional[dict] = None
    ) -> tuple[models.Device, str]:
        """
        Create a new device with a generated API key.
        Returns tuple of (device, plain_api_key).
        
        Note: The plain API key is only available at creation time.
        The stored encrypted_api_key is what will be compared during auth.
        """
        # Check if device with this name already exists
        existing_query = select(models.Device).where(models.Device.name == name)
        result = await session.exec(existing_query)
        if result.first():
            raise ValueError(f"Device with name '{name}' already exists")
        
        # Generate API key
        api_key = DeviceService.generate_api_key()
        
        # For now, we store the key directly. In production, consider hashing.
        # Store a hashed version of the API key for security (deterministic SHA-256)
        db_device = models.Device(
            name=name,
            type=device_type,
            encrypted_api_key=hash_api_key(api_key),
            client_metadata=client_metadata or {}
        )
        
        session.add(db_device)
        await session.commit()
        await session.refresh(db_device)
        
        return db_device, api_key

    @staticmethod
    async def get_all_devices(session: AsyncSession) -> List[models.Device]:
        """Get all registered devices"""
        query = select(models.Device).order_by(models.Device.name)
        result = await session.exec(query)
        return list(result.all())

    @staticmethod
    async def get_device_by_id(session: AsyncSession, device_id: int) -> Optional[models.Device]:
        """Get a device by ID"""
        return await session.get(models.Device, device_id)

    @staticmethod
    async def update_device(
        session: AsyncSession,
        device_id: int,
        name: Optional[str] = None,
        device_type: Optional[str] = None,
        client_metadata: Optional[dict] = None
    ) -> Optional[models.Device]:
        """Update device information (name, type, metadata)"""
        device = await session.get(models.Device, device_id)
        if not device:
            return None
        
        # Check for name conflicts if name is being changed
        if name and name != device.name:
            existing_query = select(models.Device).where(models.Device.name == name)
            result = await session.exec(existing_query)
            if result.first():
                raise ValueError(f"Device with name '{name}' already exists")
            device.name = name
        
        if device_type is not None:
            device.type = device_type
        
        if client_metadata is not None:
            device.client_metadata = client_metadata
        
        session.add(device)
        await session.commit()
        await session.refresh(device)
        
        return device

    @staticmethod
    async def delete_device(session: AsyncSession, device_id: int) -> bool:
        """Delete a device. Returns True if deleted, False if not found."""
        device = await session.get(models.Device, device_id)
        if not device:
            return False
        
        await session.delete(device)
        await session.commit()
        return True

    @staticmethod
    async def rotate_device_key(
        session: AsyncSession,
        device_id: int
    ) -> tuple[models.Device, str]:
        """
        Rotate the API key for a device.
        Returns tuple of (device, new_plain_api_key).
        """
        device = await session.get(models.Device, device_id)
        if not device:
            raise ValueError(f"Device with ID {device_id} not found")
        
        # Generate new API key
        new_api_key = DeviceService.generate_api_key()
        device.encrypted_api_key = hash_api_key(new_api_key)
        
        session.add(device)
        await session.commit()
        await session.refresh(device)
        
        return device, new_api_key


class EmbeddingService:
    """Helpers to create and search embeddings for events."""

    @staticmethod
    async def ensure_event_embedding(
        session: AsyncSession,
        *,
        event_id: int,
        actor_id: int,
        provider_slug: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Optional[models.EventEmbedding]:
        """
        If no embedding exists for the event, compute one for the event summary
        and persist it. Returns the EventEmbedding or None if summary missing.
        """
        event = await session.get(models.Event, event_id)
        if not event:
            return None

        # Skip superseded events
        if getattr(event, "superseded_by_event_id", None):
            return None

        # Already embedded?
        stmt_existing = select(models.EventEmbedding).where(models.EventEmbedding.event_id == event_id)
        existing = (await session.exec(stmt_existing)).one_or_none()
        if existing:
            return existing

        text = event.summary or None
        if not text:
            return None

        # Resolve defaults from settings if not provided
        from .core.config import settings  # type: ignore
        # Prefer DB-backed settings when available
        db_settings = (
            await session.exec(
                select(models.AISettings).where(models.AISettings.id == 1)
            )
        ).one_or_none()
        provider_slug_final: str = provider_slug or (
            db_settings.default_embedding_provider_slug
            if db_settings and db_settings.default_embedding_provider_slug
            else getattr(settings, "DEFAULT_EMBEDDING_PROVIDER_SLUG")
        )
        model_final: str = model or (
            db_settings.default_embedding_model
            if db_settings and db_settings.default_embedding_model
            else getattr(settings, "DEFAULT_EMBEDDING_MODEL")
        )

        vectors, usage_id = await ai_service.embed_texts(
            session,
            provider_slug=provider_slug_final,
            model=model_final,
            texts=[text],
            actor_id=actor_id,
            event_id=event_id,
        )

        emb = models.EventEmbedding(
            event_id=event_id,
            actor_id=actor_id,
            embedding=vectors[0],
            ai_usage_log_id=usage_id,
        )
        session.add(emb)
        await session.commit()
        await session.refresh(emb)
        return emb

    @staticmethod
    async def search_events_by_text(
        session: AsyncSession,
        *,
        query_text: str,
        limit: int = 20,
        provider_slug: Optional[str] = None,
        model: Optional[str] = None,
    ) -> list[tuple[models.Event, float]]:
        """Embed the query text and return events ranked by vector distance."""
        from .core.config import settings  # type: ignore
        db_settings = (
            await session.exec(
                select(models.AISettings).where(models.AISettings.id == 1)
            )
        ).one_or_none()
        provider_slug_final: str = provider_slug or (
            db_settings.default_embedding_provider_slug
            if db_settings and db_settings.default_embedding_provider_slug
            else getattr(settings, "DEFAULT_EMBEDDING_PROVIDER_SLUG")
        )
        model_final: str = model or (
            db_settings.default_embedding_model
            if db_settings and db_settings.default_embedding_model
            else getattr(settings, "DEFAULT_EMBEDDING_MODEL")
        )

        vectors, _usage_id = await ai_service.embed_texts(
            session,
            provider_slug=provider_slug_final,
            model=model_final,
            texts=[query_text],
        )
        query_vec = vectors[0]

        # Build similarity query using pgvector; ensure parameter is typed as Vector
        from sqlalchemy import literal
        from pgvector.sqlalchemy import Vector as PGVector
        # Determine target dimension from DB settings or config
        dim = (
            int(db_settings.default_embedding_dim)
            if db_settings and db_settings.default_embedding_dim
            else int(getattr(settings, "DEFAULT_EMBEDDING_DIM", 1536))
        )
        dist = func.l2_distance(
            models.EventEmbedding.embedding,
            literal(query_vec, type_=PGVector(dim)),
        ).label("distance")  # type: ignore[arg-type]
        stmt = (
            select(models.Event, dist)
            .join(models.EventEmbedding, models.EventEmbedding.event_id == models.Event.id)  # type: ignore[arg-type]
            .where(models.Event.superseded_by_event_id.is_(None))  # type: ignore[attr-defined]
            .order_by(dist)
            .limit(limit)
        )
        result = await session.exec(stmt)
        rows = result.all()
        # rows are tuples (Event, distance)
        return [(row[0], float(row[1])) for row in rows]


class AIConfigService:
    """Manage AI configuration defaults and providers."""

    @staticmethod
    async def get_ai_settings(session: AsyncSession) -> models.AISettings:
        # Try fetch existing settings row; if missing, create with app defaults
        settings_row = (
            await session.exec(select(models.AISettings).where(models.AISettings.id == 1))
        ).one_or_none()
        if settings_row:
            return settings_row
        from .core.config import settings as app_settings  # type: ignore
        settings_row = models.AISettings(
            id=1,
            default_embedding_provider_slug=getattr(app_settings, "DEFAULT_EMBEDDING_PROVIDER_SLUG", None),
            default_embedding_model=getattr(app_settings, "DEFAULT_EMBEDDING_MODEL", None),
            default_embedding_dim=getattr(app_settings, "DEFAULT_EMBEDDING_DIM", None),
        )
        session.add(settings_row)
        await session.commit()
        await session.refresh(settings_row)
        return settings_row

    @staticmethod
    async def update_ai_settings(
        session: AsyncSession,
        *,
        default_embedding_provider_slug: Optional[str] = None,
        default_embedding_model: Optional[str] = None,
        default_embedding_dim: Optional[int] = None,
    ) -> models.AISettings:
        settings_row = await AIConfigService.get_ai_settings(session)
        if default_embedding_provider_slug is not None:
            settings_row.default_embedding_provider_slug = default_embedding_provider_slug
        if default_embedding_model is not None:
            settings_row.default_embedding_model = default_embedding_model
        if default_embedding_dim is not None:
            settings_row.default_embedding_dim = int(default_embedding_dim)
        session.add(settings_row)
        await session.commit()
        await session.refresh(settings_row)
        return settings_row

    @staticmethod
    async def list_providers(session: AsyncSession) -> list[models.AIProvider]:
        result = await session.exec(select(models.AIProvider))
        return list(result.all())

    @staticmethod
    async def update_provider(
        session: AsyncSession,
        provider_id: int,
        *,
        name: Optional[str] = None,
        model_path_or_uri: Optional[str] = None,
        is_active: Optional[bool] = None,
        config: Optional[dict] = None,
    ) -> Optional[models.AIProvider]:
        provider = await session.get(models.AIProvider, provider_id)
        if not provider:
            return None
        if name is not None:
            provider.name = name
        if model_path_or_uri is not None:
            provider.model_path_or_uri = model_path_or_uri
        if is_active is not None:
            provider.is_active = is_active
        if config is not None:
            provider.config = config
        session.add(provider)
        await session.commit()
        await session.refresh(provider)
        return provider
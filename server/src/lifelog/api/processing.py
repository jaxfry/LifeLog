from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import logging

from ..dependencies import get_session
from pathlib import Path
from ..services import ProcessingService, ProcessingRoutingService
from ..core.actors import actor_registry
from ..core.config import settings
from ..auth import require_auth  # Add authentication for internal APIs

router = APIRouter(
    prefix="/processing",
    tags=["Processing"],
)

logger = logging.getLogger(__name__)


# Helper to schedule async background coroutines from FastAPI BackgroundTasks
def schedule_async(coro_func, *args, **kwargs):
    """Schedule an async callable to run on the current event loop.

    BackgroundTasks expects a sync callable. This wrapper schedules the
    provided async function on the running loop without blocking the request.
    """
    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(coro_func(*args, **kwargs))


# ============================================================================
# ACTOR ROUTING ENDPOINTS
# ============================================================================

class ActorRoutingItem(BaseModel):
    """Actor routing mapping."""
    source_actor_slug: str
    processor_actor_slug: str
    source: str  # "database" or "config"
    route_id: Optional[int] = None


class ActorRoutingListResponse(BaseModel):
    """List of all actor routing mappings."""
    routings: List[ActorRoutingItem]
    total: int
    db_count: int
    config_count: int


class CreateRoutingRequest(BaseModel):
    """Request to create a new actor routing."""
    source_actor_slug: str
    processor_actor_slug: str


class CreateRoutingResponse(BaseModel):
    """Response after creating an actor routing."""
    route_id: int
    source_actor_slug: str
    processor_actor_slug: str
    message: str


@router.get("/actor-routing", response_model=ActorRoutingListResponse)
async def list_actor_routings(
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    List all actor routing mappings.
    
    Shows both database-configured and config-file-based routings.
    Database routings take precedence over config routings.
    """
    routings = await ProcessingRoutingService.get_all_routings(session)
    
    db_count = sum(1 for r in routings if r["source"] == "database")
    config_count = sum(1 for r in routings if r["source"] == "config")
    
    return ActorRoutingListResponse(
        routings=[ActorRoutingItem(**r) for r in routings],
        total=len(routings),
        db_count=db_count,
        config_count=config_count
    )


@router.post("/actor-routing", response_model=CreateRoutingResponse, status_code=status.HTTP_201_CREATED)
async def create_actor_routing(
    request: CreateRoutingRequest,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Create a new actor routing mapping in the database.
    
    This maps a source actor to a processor actor. When data is ingested
    from the source actor, it will be automatically routed to the specified
    processor for processing.
    
    Database routings override any config-based routings for the same source.
    """
    try:
        routing = await ProcessingRoutingService.create_routing(
            session,
            request.source_actor_slug,
            request.processor_actor_slug
        )
        
        return CreateRoutingResponse(
            route_id=routing.id,  # type: ignore
            source_actor_slug=request.source_actor_slug,
            processor_actor_slug=request.processor_actor_slug,
            message=f"Successfully created routing: {request.source_actor_slug} → {request.processor_actor_slug}"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/actor-routing/{route_id}", status_code=status.HTTP_200_OK)
async def delete_actor_routing(
    route_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Delete an actor routing by ID.
    
    Only database routings can be deleted. Config-based routings must be
    removed from the configuration file.
    """
    deleted = await ProcessingRoutingService.delete_routing(session, route_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Routing with ID {route_id} not found")
    
    return {
        "message": f"Successfully deleted routing {route_id}",
        "route_id": route_id
    }


# ============================================================================
# PROCESSING TRIGGER ENDPOINTS
# ============================================================================


from typing import Optional


def _parse_iso(s: Optional[str]) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    # Handle trailing 'Z'
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)

@router.post("/trigger/{raw_log_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_processing(
    raw_log_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)  # Protect internal API
):
    """
    Manually triggers the processing pipeline for a single raw log.
    Uses service layer to abstract database operations.
    NOTE: In production, this will be replaced by an async task queue.
    """
    # Use service layer to get raw log with source actor
    raw_log = await ProcessingService.get_raw_log_with_source_actor(session, raw_log_id)
    
    if not raw_log:
        raise HTTPException(status_code=404, detail="RawLog not found")

    # Resolve processor via DB mapping, fallback to config
    source_actor_slug = raw_log.source_actor.slug
    processor_slug = await ProcessingRoutingService.resolve_processor_slug(session, source_actor_slug)

    if not processor_slug:
        return {"status": "ok", "detail": f"No processor mapped for source '{source_actor_slug}'"}

    # Prefer in-process registered code; otherwise try external runner
    ActorClass = actor_registry.get_actor_class(processor_slug)
    if ActorClass:
        actor_instance = ActorClass()
        await actor_instance.run(data=raw_log)
    else:
        # Fallback to external execution if configured
        from sqlmodel import select
        from .. import models
        from ..core.isolated_runner import run_external_actor, IsolationError
        # Find processor actor model and owning extension
        # Note: Multiple actors can have the same slug (different versions/extensions)
        proc_result = await session.exec(select(models.Actor).where(models.Actor.slug == processor_slug))
        proc_models = proc_result.all()
        if not proc_models:
            raise HTTPException(status_code=500, detail=f"Processor actor '{processor_slug}' not found")
        proc_model = proc_models[0]  # Use first match
        ext = await session.get(models.Extension, proc_model.extension_id)
        if not ext or not ext.config:
            raise HTTPException(status_code=500, detail="Extension config missing for external execution")
        if ext.config.get("execution_mode") != "external":
            raise HTTPException(status_code=500, detail=f"Code for actor '{processor_slug}' not registered and extension not marked external")
        ext_dir = ext.config.get("store_path")
        if not ext_dir:
            raise HTTPException(status_code=500, detail="External extension store_path not set")
        # Normalize path to absolute inside container to avoid CWD issues
        try:
            ext_dir_path = Path(ext_dir).resolve()
        except Exception:
            ext_dir_path = Path(ext_dir)
        allow_network = bool(ext.config.get("allow_network", False))
        # Build sanitized payload for the worker
        payload = {
            "raw_log": {
                "id": raw_log.id,
                "source_actor_slug": raw_log.source_actor.slug if raw_log.source_actor else None,
                "raw_data": raw_log.raw_data,
                "ingested_at": raw_log.ingested_at.isoformat() if raw_log.ingested_at else None,
            }
        }
        try:
            actions = run_external_actor(ext_dir_path, processor_slug, payload, allow_network=allow_network)
        except IsolationError as e:
            raise HTTPException(status_code=500, detail=str(e))
        # Apply actions produced by the external actor (create event, metadata, etc.)
        from ..services import EventService
        from .. import models as _m
        # Minimal supported action: create_event
        created_event_id = None
        if actions and isinstance(actions, dict) and actions.get("create_event"):
            ev = actions["create_event"]
            # resolve event type
            et = (await session.exec(select(_m.EventType).where(_m.EventType.slug == ev.get("event_type", "")))).one_or_none()
            if not et:
                raise HTTPException(status_code=400, detail=f"Unknown event_type '{ev.get('event_type')}' from external actor")
            new_event = _m.Event(
                processor_actor_id=proc_model.id,  # type: ignore[arg-type]
                start_time=_parse_iso(ev.get("start_time")),
                end_time=_parse_iso(ev.get("end_time")) if ev.get("end_time") else None,
                event_type_id=et.id,  # type: ignore[arg-type]
                summary=ev.get("summary"),
            )
            session.add(new_event)
            await session.flush()
            await session.refresh(new_event)
            # link to raw log
            link = _m.EventRawLogLink(event_id=new_event.id, raw_log_id=raw_log.id)  # type: ignore[arg-type]
            session.add(link)
            await session.commit()
            created_event_id = new_event.id
        return {"status": "processing triggered", "mode": "external", "event_id": created_event_id}

    return {"status": "processing triggered"}


class DateRangeFilter(BaseModel):
    """Date range filter for reprocessing."""
    start: Optional[datetime] = None
    end: Optional[datetime] = None


class ReprocessActorRequest(BaseModel):
    """Request to reprocess actor data."""
    date_range: Optional[DateRangeFilter] = None
    dry_run: bool = True  # Safety default: don't actually reprocess unless explicit


class ReprocessActorResponse(BaseModel):
    """Response after queuing actor reprocessing."""
    message: str
    actor_slug: str
    current_version: str
    raw_logs_queued: int
    date_range: Optional[dict] = None


class CostEstimateResponse(BaseModel):
    """Response with cost estimation for reprocessing."""
    raw_logs_affected: int
    estimated_ai_calls: int
    estimated_cost_usd: float
    estimated_duration_minutes: int
    current_version: str
    date_range: Optional[dict] = None


@router.post("/estimate/{actor_slug}", response_model=CostEstimateResponse)
async def estimate_reprocessing_cost(
    actor_slug: str,
    request: Optional[ReprocessActorRequest] = None,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Estimate the cost and scope of reprocessing before actually doing it.
    
    This endpoint helps users make informed decisions about whether to reprocess
    historical data after an extension upgrade. It calculates:
    - Number of raw_logs affected
    - Estimated AI API calls (and cost)
    - Estimated processing time
    
    Use this before calling reprocess-actor to understand the impact.
    """
    try:
        start_date = None
        end_date = None
        if request and request.date_range:
            start_date = request.date_range.start
            end_date = request.date_range.end
        
        estimate = await ProcessingService.estimate_reprocessing_cost(
            session,
            actor_slug,
            start_date=start_date,
            end_date=end_date
        )
        
        return CostEstimateResponse(**estimate)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/reprocess-actor/{actor_slug}", response_model=ReprocessActorResponse, status_code=status.HTTP_202_ACCEPTED)
async def reprocess_actor(
    actor_slug: str,
    request: ReprocessActorRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Queue reprocessing for raw_logs previously processed by older versions of an actor.
    
    This endpoint is typically called after an extension upgrade to regenerate events
    with the new actor logic. The original events are superseded, not deleted.
    
    **Safety Features**:
    - `dry_run=true` (default): Only estimates, doesn't actually reprocess
    - `date_range`: Optionally limit reprocessing to a specific time window
    
    **Workflow**:
    1. Call `/estimate/{actor_slug}` to see cost/scope
    2. If acceptable, call this endpoint with `dry_run=false`
    3. Monitor progress via processing logs
    
    **Note**: This uses background tasks. In production, use a proper queue (Celery/RQ).
    """
    from sqlmodel import select
    from .. import models
    
    # Get the actor and its current version
    actor_stmt = select(models.Actor).where(models.Actor.slug == actor_slug)
    actor = (await session.exec(actor_stmt)).one_or_none()
    if not actor:
        raise HTTPException(status_code=404, detail=f"Actor '{actor_slug}' not found")

    current_version = actor.version
    
    # Extract date range if provided
    start_date = None
    end_date = None
    if request.date_range:
        start_date = request.date_range.start
        end_date = request.date_range.end

    # Find raw_logs to reprocess
    raw_log_ids = await ProcessingService.find_raw_logs_for_reprocessing(
        session,
        actor_slug,
        current_version,
        start_date=start_date,
        end_date=end_date
    )

    if not raw_log_ids:
        return ReprocessActorResponse(
            message=f"No raw_logs found for reprocessing (all already at version {current_version})",
            actor_slug=actor_slug,
            current_version=current_version,
            raw_logs_queued=0,
            date_range={
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            } if (start_date or end_date) else None
        )
    
    # If dry_run, just return the estimate
    if request.dry_run:
        return ReprocessActorResponse(
            message=f"[DRY RUN] Would queue {len(raw_log_ids)} raw_logs for reprocessing. Set dry_run=false to execute.",
            actor_slug=actor_slug,
            current_version=current_version,
            raw_logs_queued=len(raw_log_ids),
            date_range={
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            } if (start_date or end_date) else None
        )

    # Background task to reprocess each raw_log
    async def _reprocess_raw_logs():
        from ..db import async_session
        for raw_log_id in raw_log_ids:
            async with async_session() as bg_session:
                raw_log = await ProcessingService.get_raw_log_with_source_actor(bg_session, raw_log_id)
                if not raw_log:
                    continue

                ActorClass = actor_registry.get_actor_class(actor_slug)
                if not ActorClass:
                    logger.warning(f"Actor code '{actor_slug}' not registered; skipping raw_log_id={raw_log_id}")
                    continue

                try:
                    actor_instance = ActorClass()
                    await actor_instance.run(data=raw_log)
                except Exception as e:
                    logger.error(f"Reprocessing failed for raw_log_id={raw_log_id}: {e}")

    background_tasks.add_task(_reprocess_raw_logs)

    return ReprocessActorResponse(
        message=f"Queued {len(raw_log_ids)} raw_logs for reprocessing with actor version {current_version}",
        actor_slug=actor_slug,
        current_version=current_version,
        raw_logs_queued=len(raw_log_ids),
        date_range={
            "start": start_date.isoformat() if start_date else None,
            "end": end_date.isoformat() if end_date else None
        } if (start_date or end_date) else None
    )


# ============================================================================
# BATCH PROCESSING ENDPOINTS
# ============================================================================


class BatchProcessRequest(BaseModel):
    """Request to batch process unprocessed raw logs."""
    limit: int = 100
    source_actor_slug: Optional[str] = None
    since: Optional[datetime] = None


class BatchProcessResponse(BaseModel):
    """Response after batch processing."""
    status: str
    message: str
    processed: int
    failed: int
    skipped: int


@router.post("/batch-process", response_model=BatchProcessResponse, status_code=status.HTTP_202_ACCEPTED)
async def batch_process_raw_logs(
    request: BatchProcessRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Process unprocessed raw logs in batches.
    
    This endpoint finds raw logs that haven't been processed yet and processes
    them in batches to avoid connection pool exhaustion. It's designed to be
    called periodically (e.g., via cron) or manually when ingestion is paused.
    
    **Parameters**:
    - `limit`: Maximum number of raw logs to process (default: 100)
    - `source_actor_slug`: Only process logs from this source (optional)
    - `since`: Only process logs ingested after this time (optional)
    
    **Features**:
    - Processes logs in small batches with separate sessions
    - Limits concurrent processing to prevent pool exhaustion
    - Returns immediately, processes in background
    - Safe to call repeatedly (skips already-processed logs)
    """
    from sqlmodel import select
    from .. import models
    
    # Build query for unprocessed raw logs
    stmt = select(models.RawLog.id).order_by(models.RawLog.ingested_at)  # type: ignore
    
    # Filter by source actor if specified
    if request.source_actor_slug:
        actor_stmt = select(models.Actor).where(models.Actor.slug == request.source_actor_slug)
        actor = (await session.exec(actor_stmt)).first()
        if actor and actor.id:
            stmt = stmt.where(models.RawLog.source_actor_id == actor.id)
    
    # Filter by time if specified
    if request.since:
        stmt = stmt.where(models.RawLog.ingested_at >= request.since)
    
    # Get raw log IDs (limit to requested amount)
    stmt = stmt.limit(request.limit)
    result = await session.exec(stmt)
    raw_log_ids = list(result.all())
    
    if not raw_log_ids:
        return BatchProcessResponse(
            status="completed",
            message="No raw logs found to process",
            processed=0,
            failed=0,
            skipped=0
        )
    
    # Background task to process in batches
    async def _batch_process():
        from ..db import async_session
        import asyncio

        processed = 0
        failed = 0
        skipped = 0
        batch_size = 10  # Process 10 at a time to avoid pool exhaustion

        logger.warning(f"[batch] Starting batch processing of {len(raw_log_ids)} raw logs")

        for i in range(0, len(raw_log_ids), batch_size):
            batch = raw_log_ids[i:i + batch_size]
            logger.warning(
                f"[batch] Processing batch {i // batch_size + 1}/{(len(raw_log_ids) - 1) // batch_size + 1} ({len(batch)} logs)"
            )

            # Process each log in the batch with its own session
            for raw_log_id_val in batch:
                if not raw_log_id_val:
                    skipped += 1
                    continue

                raw_log_id = int(raw_log_id_val)  # Ensure it's an int

                try:
                    async with async_session() as bg_session:
                        # Load raw log with source actor
                        raw_log = await ProcessingService.get_raw_log_with_source_actor(bg_session, raw_log_id)
                        if not raw_log:
                            skipped += 1
                            continue

                        # Check if already processed (has successful processing log)
                        from ..constants import ProcessingStatus
                        check_stmt = (
                            select(models.ActorProcessingLog)
                            .where(
                                models.ActorProcessingLog.raw_log_id == raw_log_id,
                                models.ActorProcessingLog.status == ProcessingStatus.SUCCESS.value,
                            )
                            .limit(1)
                        )
                        existing = (await bg_session.exec(check_stmt)).first()
                        if existing:
                            logger.debug(f"Raw log {raw_log_id} already processed, skipping")
                            skipped += 1
                            continue

                        # Resolve processor
                        source_actor_slug = raw_log.source_actor.slug
                        processor_slug = await ProcessingRoutingService.resolve_processor_slug(
                            bg_session, source_actor_slug
                        )

                        if not processor_slug:
                            logger.debug(f"No processor mapped for {source_actor_slug}, skipping")
                            skipped += 1
                            continue

                        # Get actor class
                        ActorClass = actor_registry.get_actor_class(processor_slug)
                        if not ActorClass:
                            logger.warning(f"Actor {processor_slug} not registered, skipping")
                            skipped += 1
                            continue

                        # Process the log
                        try:
                            actor_instance = ActorClass()
                            await actor_instance.run(data=raw_log)
                            processed += 1
                            logger.warning(f"[batch] Successfully processed raw_log {raw_log_id}")
                            
                            # Record processing success in the batch session
                            # (Actors may also write their own logs, but this ensures consistency)
                            try:
                                # Get the processor actor model
                                proc_stmt = select(models.Actor).where(models.Actor.slug == processor_slug).limit(1)
                                proc_actor = (await bg_session.exec(proc_stmt)).first()
                                if proc_actor and proc_actor.id is not None:
                                    processing_log = models.ActorProcessingLog(
                                        actor_id=proc_actor.id,
                                        actor_version_at_processing=proc_actor.version,
                                        raw_log_id=raw_log_id,
                                        status=ProcessingStatus.SUCCESS.value,
                                        details={"batch_id": "manual", "source": "batch_processor"},
                                    )
                                    bg_session.add(processing_log)
                                    await bg_session.commit()
                            except Exception as log_err:
                                logger.warning(f"Failed to write processing log for raw_log {raw_log_id}: {log_err}")
                        except Exception as e:
                            failed += 1
                            logger.error(f"Failed to process raw_log {raw_log_id}: {e}", exc_info=True)
                            
                            # Record processing failure
                            try:
                                proc_stmt = select(models.Actor).where(models.Actor.slug == processor_slug).limit(1)
                                proc_actor = (await bg_session.exec(proc_stmt)).first()
                                if proc_actor and proc_actor.id is not None:
                                    processing_log = models.ActorProcessingLog(
                                        actor_id=proc_actor.id,
                                        actor_version_at_processing=proc_actor.version,
                                        raw_log_id=raw_log_id,
                                        status=ProcessingStatus.FAILURE.value,
                                        details={"error": str(e), "source": "batch_processor"},
                                    )
                                    bg_session.add(processing_log)
                                    await bg_session.commit()
                            except Exception as log_err:
                                logger.warning(f"Failed to write failure log for raw_log {raw_log_id}: {log_err}")

                except Exception as e:
                    failed += 1
                    logger.error(f"Error processing raw_log {raw_log_id}: {e}", exc_info=True)

            # Small delay between batches to allow pool to recover
            if i + batch_size < len(raw_log_ids):
                await asyncio.sleep(0.5)

        logger.warning(f"[batch] Complete: {processed} processed, {failed} failed, {skipped} skipped")
    
    # Schedule async batch processing on the current event loop
    import asyncio as _asyncio
    _asyncio.create_task(_batch_process())
    
    return BatchProcessResponse(
        status="queued",
        message=f"Batch processing queued for up to {len(raw_log_ids)} raw logs",
        processed=0,
        failed=0,
        skipped=0
    )


@router.post("/batch-process/all-unprocessed", response_model=BatchProcessResponse, status_code=status.HTTP_202_ACCEPTED)
async def batch_process_all_unprocessed(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Convenience endpoint to process all unprocessed raw logs.
    
    Processes in batches of 100 to avoid overwhelming the system.
    Safe to call multiple times.
    """
    request = BatchProcessRequest(limit=100)
    return await batch_process_raw_logs(request, background_tasks, session, current_user)


# ============================================================================
# BATCH STATUS ENDPOINTS
# ============================================================================


class BatchStatusResponse(BaseModel):
    total_raw_logs: int
    processed_success_total: int
    pending_estimate: int
    processed_last_10_min: int
    failures_last_10_min: int
    recent_logs: list[dict]


@router.get("/batch-process/status", response_model=BatchStatusResponse)
async def get_batch_status(
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Get a quick snapshot of batch processing progress and recent activity.

    - total_raw_logs: total number of raw logs ingested
    - processed_success_total: number of raw logs with a SUCCESS processing log
    - pending_estimate: total_raw_logs - processed_success_total
    - processed_last_10_min: SUCCESS logs in last 10 minutes
    - failures_last_10_min: FAILURE logs in last 10 minutes
    - recent_logs: last 20 processing logs (status, raw_log_id, actor_slug, when)
    """
    from sqlmodel import select
    from sqlalchemy import func, desc
    from .. import models
    from ..constants import ProcessingStatus
    from datetime import datetime, timezone, timedelta

    # Total raw logs (use select_from to avoid Optional typing issues)
    total_stmt = select(func.count()).select_from(models.RawLog)
    total_raw_logs = int((await session.exec(total_stmt)).one())

    # Raw logs with SUCCESS (approximate; counts rows, typically one per raw_log)
    success_count_stmt = (
        select(func.count())
        .select_from(models.ActorProcessingLog)
        .where(
            models.ActorProcessingLog.status == ProcessingStatus.SUCCESS.value,
            models.ActorProcessingLog.raw_log_id.is_not(None)  # type: ignore[attr-defined]
        )
    )
    processed_success_total = int((await session.exec(success_count_stmt)).one())

    pending_estimate = max(0, total_raw_logs - processed_success_total)

    # Recent window
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=10)

    processed_last_stmt = (
        select(func.count())
        .select_from(models.ActorProcessingLog)
        .where(
            models.ActorProcessingLog.status == ProcessingStatus.SUCCESS.value,
            models.ActorProcessingLog.processed_at >= window_start
        )
    )
    processed_last_10_min = int((await session.exec(processed_last_stmt)).one())

    failures_last_stmt = (
        select(func.count())
        .select_from(models.ActorProcessingLog)
        .where(
            models.ActorProcessingLog.status == ProcessingStatus.FAILURE.value,
            models.ActorProcessingLog.processed_at >= window_start
        )
    )
    failures_last_10_min = int((await session.exec(failures_last_stmt)).one())

    # Recent logs (without join to avoid typing issues)
    recent_stmt = (
        select(
            models.ActorProcessingLog.raw_log_id,
            models.ActorProcessingLog.status,
            models.ActorProcessingLog.processed_at,
            models.ActorProcessingLog.actor_id,
        )
        .limit(20)
    )
    recent_rows = (await session.exec(recent_stmt)).all()
    recent_logs = [
        {
            "raw_log_id": row[0],
            "status": row[1],
            "processed_at": row[2].isoformat() if row[2] else None,
            "actor_id": row[3],
        }
        for row in recent_rows
    ]

    return BatchStatusResponse(
        total_raw_logs=total_raw_logs,
        processed_success_total=processed_success_total,
        pending_estimate=pending_estimate,
        processed_last_10_min=processed_last_10_min,
        failures_last_10_min=failures_last_10_min,
        recent_logs=recent_logs,
    )

# ============================================================================
# TIMELINE GENERATION ENDPOINTS
# ============================================================================


class GenerateTimelineRequest(BaseModel):
    """Request to generate timeline blocks for a period."""
    start_time: datetime
    end_time: datetime
    model: Optional[str] = None
    force_regenerate: bool = False
    max_characters_per_chunk: int = 4000


class GenerateTimelineResponse(BaseModel):
    """Response after generating timeline blocks."""
    status: str
    message: str
    blocks_created: int
    chunks_processed: int
    period: dict


@router.post("/generate-timeline", response_model=GenerateTimelineResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_timeline(
    request: GenerateTimelineRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Generate timeline blocks for a specified time period.
    
    This endpoint uses the timeline-enricher actor to:
    1. Chunk events intelligently with budget enforcement
    2. Generate AI-enriched timeline blocks via LLM
    3. Optionally supersede existing blocks (if force_regenerate=true)
    
    Timeline blocks combine multiple raw events into concise, human-readable
    summaries with context, making it easier to understand what happened.
    
    **Note**: This operation is queued as a background task. For large periods,
    it may take several minutes.
    """
    from sqlmodel import select
    from .. import models
    from ..core.actors import actor_registry
    
    # Find timeline-enricher actor
    actor_stmt = select(models.Actor).where(models.Actor.slug == "timeline-enricher")
    actor = (await session.exec(actor_stmt)).first()
    if not actor:
        raise HTTPException(status_code=404, detail="timeline-enricher actor not found")
    
    # Prepare data for actor
    actor_data = {
        "start_time": request.start_time,
        "end_time": request.end_time,
        "model": request.model,
        "force_regenerate": request.force_regenerate,
        "budget": {
            "max_characters": request.max_characters_per_chunk
        }
    }
    
    # Check if actor is registered in code
    ActorClass = actor_registry.get_actor_class("timeline-enricher")
    if not ActorClass:
        raise HTTPException(
            status_code=500,
            detail="timeline-enricher code not loaded. Ensure the enrichers module is imported."
        )
    
    # Run in background
    async def _generate_timeline():
        try:
            actor_instance = ActorClass()
            result = await actor_instance.run(actor_data)
            logger.info(f"Timeline generation completed: {result}")
        except Exception as e:
            logger.error(f"Timeline generation failed: {e}", exc_info=True)
    
    # Schedule async timeline generation on the current event loop
    import asyncio as _asyncio
    _asyncio.create_task(_generate_timeline())
    
    return GenerateTimelineResponse(
        status="queued",
        message=f"Timeline generation queued for {request.start_time.date()} to {request.end_time.date()}",
        blocks_created=0,
        chunks_processed=0,
        period={
            "start": request.start_time.isoformat(),
            "end": request.end_time.isoformat()
        }
    )


@router.post("/generate-timeline/yesterday", response_model=GenerateTimelineResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_timeline_yesterday(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(require_auth)
):
    """
    Convenience endpoint to generate timeline blocks for yesterday.
    
    This is the most common use case for automated daily timeline generation.
    """
    from datetime import timezone
    end_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start_time = end_time - timedelta(days=1)
    
    request = GenerateTimelineRequest(
        start_time=start_time,
        end_time=end_time,
        force_regenerate=False
    )
    
    return await generate_timeline(request, background_tasks, session, current_user)

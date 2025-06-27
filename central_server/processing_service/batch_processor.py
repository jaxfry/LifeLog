import asyncio
from datetime import date, timedelta, datetime
from typing import List
from zoneinfo import ZoneInfo
import argparse
import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy import select

try:
    # Try relative imports for Docker context
    from .db_session import get_db_session_async, check_db_connection_async
    from .db_models import (
        Event as EventOrm,
        Project as ProjectOrm,
        TimelineEntryOrm,
        EventKind,
    )
    from .logic.settings import settings as service_settings
    from .logic.timeline import TimelineProcessorService
    from .logic.project_resolver import ProjectResolver
    from .models import ProcessingEventData
except ImportError:
    # Fall back to absolute imports for local context
    from central_server.processing_service.db_session import get_db_session_async, check_db_connection_async
    from central_server.processing_service.db_models import (
        Event as EventOrm,
        Project as ProjectOrm,
        TimelineEntryOrm,
        EventKind,
    )
    from central_server.processing_service.logic.settings import settings as service_settings
    from central_server.processing_service.logic.timeline import TimelineProcessorService
    from central_server.processing_service.logic.project_resolver import ProjectResolver
    from central_server.processing_service.models import ProcessingEventData

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_events_for_day(db_session: AsyncSession, local_day: date) -> List[ProcessingEventData]:
    """
    Fetches all digital activity events for a specific local day from the database
    and transforms them into the ProcessingEventData format for the LLM.
    """
    result = await db_session.execute(
        select(EventOrm)
        .options(joinedload(EventOrm.digital_activity))
        .where(
            EventOrm.local_day == local_day,
            EventOrm.event_type == EventKind.DIGITAL_ACTIVITY
        )
        .order_by(EventOrm.start_time)
    )
    events_for_day = result.scalars().all()
    processing_data = []
    for event in events_for_day:
        if event.digital_activity is not None and event.end_time is not None:
            processing_data.append(
                ProcessingEventData(
                    event_id=str(event.id),
                    start_time=event.start_time, # type: ignore
                    end_time=event.end_time, # type: ignore
                    duration_s=(event.end_time - event.start_time).total_seconds(), # type: ignore
                    app=event.digital_activity.app,
                    title=event.digital_activity.title,
                    url=event.digital_activity.url,
                    event_type=event.event_type.value,
                )
            )
    return processing_data


async def run_batch_processing(target_day: date, process_at_utc: datetime | None = None):
    """
    Runs the daily batch processing for a specific day.

    Args:
        target_day: The local day to process events for.
        process_at_utc: If provided, this UTC datetime will be used to determine
                        if processing should run, overriding the daily 3 AM check.
                        This is for on-demand script execution.
    """
    logger.info(f"Starting batch processing for local day: {target_day}")

    if not await check_db_connection_async():
        logger.error("Database connection failed. Aborting batch processing.")
        return

    # If not running on-demand, check if it's the right time to run.
    if process_at_utc is None:
        local_tz = ZoneInfo(service_settings.LOCAL_TZ)
        now_local = datetime.now(local_tz)

        # scheduled_time is HH:MM, e.g., "03:00"
        run_hour, run_minute = map(int, service_settings.DAILY_PROCESSING_TIME.split(':'))

        # Today's processing time in the local timezone
        processing_time_local = now_local.replace(
            hour=run_hour, minute=run_minute, second=0, microsecond=0
        )

        # If it's already past today's processing time, then we should be processing
        # for *today*. If we are asked to process for yesterday, we can proceed.
        # If we are asked to process for today, we must wait until the time has passed.
        if target_day == now_local.date() and now_local < processing_time_local:
            logger.info(
                f"Skipping batch processing for {target_day}. "
                f"It's not yet {service_settings.DAILY_PROCESSING_TIME} in {service_settings.LOCAL_TZ}."
            )
            return
    else:
        logger.info(f"On-demand run for {target_day}, triggered at {process_at_utc}.")


    try:
        timeline_processor = TimelineProcessorService(settings=service_settings)
        logger.info("TimelineProcessorService initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize TimelineProcessorService: {e}. Aborting.", exc_info=True)
        return

    async with get_db_session_async() as db_session:
        # 1. Fetch all events for the target day.
        events_for_processing = await get_events_for_day(db_session, target_day)
        if not events_for_processing:
            logger.info(f"No events found for {target_day}. Nothing to process.")
            return

        # 2. Get known project names to guide the LLM.
        result = await db_session.execute(select(ProjectOrm.name))
        known_project_names = [row[0] for row in result.all()]

        # 3. Process the full day's events to generate timeline entries.
        timeline_pydantic_entries = timeline_processor.process_events_batch(
            source_events_data=events_for_processing,
            batch_local_day=target_day,
            known_project_names=known_project_names
        )

        # 4. Make processing idempotent: Delete old timeline entries for this day.
        await db_session.execute(
            TimelineEntryOrm.__table__.delete().where(TimelineEntryOrm.local_day == target_day)
        )
        logger.info(f"Deleted old timeline entries for {target_day} to ensure idempotency.")

        if not timeline_pydantic_entries:
            logger.info(f"Processing for {target_day} generated no new timeline entries.")
            await db_session.commit()
            return

        # 5. Store new entries and link them to their source events.
        project_resolver = ProjectResolver(db_session)
        result = await db_session.execute(select(EventOrm).where(EventOrm.local_day == target_day))
        orm_events_for_day = result.scalars().all()
        event_orm_map = {str(event.id): event for event in orm_events_for_day}

        for pydantic_entry in timeline_pydantic_entries:
            project_orm = await project_resolver.get_or_create_project_by_name(pydantic_entry.project)
            source_events_for_entry = [
                event_orm_map[proc_event.event_id]
                for proc_event in events_for_processing
                if proc_event.event_id in event_orm_map and
                   pydantic_entry.start <= proc_event.start_time < pydantic_entry.end
            ]
            db_entry = TimelineEntryOrm(
                id=uuid.uuid4(),
                start_time=pydantic_entry.start,
                end_time=pydantic_entry.end,
                title=pydantic_entry.activity,
                summary=pydantic_entry.notes,
                project=project_orm,
                source_events=source_events_for_entry
            )
            db_session.add(db_entry)
        await db_session.commit()
        logger.info(f"Successfully stored {len(timeline_pydantic_entries)} new timeline entries for {target_day}.")


async def main():
    """
    Command-line entry point for the batch processor.
    Accepts a --date argument in YYYY-MM-DD format. Defaults to yesterday.
    """
    parser = argparse.ArgumentParser(description="Run batch processing for a specific day.")
    parser.add_argument(
        "--date",
        type=str,
        help="The date to process in YYYY-MM-DD format. Defaults to yesterday."
    )
    args = parser.parse_args()

    if args.date:
        try:
            target_day = date.fromisoformat(args.date)
        except ValueError:
            logger.error("Invalid date format. Please use YYYY-MM-DD.")
            return
    else:
        # Default to yesterday based on the service's local timezone
        try:
            local_tz = ZoneInfo(service_settings.LOCAL_TZ)
        except Exception:
            logger.error(f"Invalid timezone '{service_settings.LOCAL_TZ}' in settings. Falling back to UTC.")
            local_tz = ZoneInfo("UTC")
        target_day = (datetime.now(local_tz) - timedelta(days=1)).date()

    await run_batch_processing(target_day)


if __name__ == "__main__":
    asyncio.run(main())
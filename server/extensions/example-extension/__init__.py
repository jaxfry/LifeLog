"""
Example Extension for LifeLog

This extension demonstrates:
- Dynamic actor loading via @actor_registry.register
- Managed schemas (custom tables)
- Processing raw logs into events
- Using the actor base class

Directory structure:
example-extension/
├── __init__.py (this file - registers actors)
├── manifest.json (declares extension metadata)
└── actors.py (could also put actor implementations here)
"""

import logging
from typing import Any

# Import the core actor system
# When this module is loaded by the extension loader, these imports will work
# because the extension loader adds the module to sys.modules with the right context
try:
    from lifelog.core.actors import ActorBase, ActorConfig, actor_registry
    from lifelog import models
    from lifelog.db import async_session
    from lifelog.constants import ProcessingStatus
    from sqlmodel import select
except ImportError:
    # Fallback for when running in test/dev without full server context
    import sys
    sys.path.insert(0, '../../src')
    from lifelog.core.actors import ActorBase, ActorConfig, actor_registry
    from lifelog import models
    from lifelog.db import async_session
    from lifelog.constants import ProcessingStatus
    from sqlmodel import select

logger = logging.getLogger(__name__)


@actor_registry.register(
    ActorConfig(
        slug="example-processor",
        actor_type=models.ActorType.PROCESSOR,
        version="1.0.0",
    )
)
class ExampleProcessor(ActorBase):
    """
    Example processor that demonstrates:
    - Reading raw log data
    - Creating events with event types
    - Writing to managed schema tables
    - Logging processing status
    """

    async def run(self, data: models.RawLog) -> Any:
        raw_log = data
        logger.info(f"ExampleProcessor running on raw_log_id: {raw_log.id}")

        async with async_session() as session:
            # Reload raw_log in this session
            raw_log = await session.get(models.RawLog, raw_log.id)
            if not raw_log:
                logger.error(f"RawLog id={raw_log.id} not found")
                return

            # Get actor metadata
            actor_stmt = select(models.Actor).where(models.Actor.slug == "example-processor")
            actor = (await session.exec(actor_stmt)).one_or_none()
            if not actor or actor.id is None:
                logger.error("Could not find example-processor in database")
                return

            actor_id = actor.id
            actor_version = actor.version

            # Get event type
            event_type_stmt = select(models.EventType).where(
                models.EventType.slug == "example-activity"
            )
            event_type = (await session.exec(event_type_stmt)).one_or_none()

            if not event_type or not event_type.id:
                logger.error("EventType 'example-activity' not found")
                # Log failure
                session.add(
                    models.ActorProcessingLog(
                        actor_id=actor_id,
                        actor_version_at_processing=actor_version,
                        raw_log_id=raw_log.id,
                        status=ProcessingStatus.FAILURE,
                        details={"reason": "missing_event_type"},
                    )
                )
                await session.commit()
                return

            # Extract data from raw log
            activity_type = raw_log.raw_data.get("activity_type", "unknown")
            summary = raw_log.raw_data.get("summary", "Example activity")

            # Create event
            new_event = models.Event(
                processor_actor_id=actor_id,
                start_time=raw_log.ingested_at,
                event_type_id=event_type.id,
                summary=summary,
            )

            # Link to raw log
            new_event.raw_logs.append(raw_log)
            session.add(new_event)

            # Flush to get event ID
            await session.flush()
            event_id = new_event.id

            if event_id:
                # Write to managed schema table (example_extension_activity_details)
                # Note: We use raw SQL here since the table is dynamically created
                from sqlalchemy import text, bindparam
                from sqlalchemy.dialects.postgresql import JSONB
                
                insert_stmt = text("""
                    INSERT INTO example_extension_activity_details 
                    (event_id, activity_type, metadata)
                    VALUES (:event_id, :activity_type, :metadata)
                """).bindparams(bindparam("metadata", type_=JSONB))
                
                await session.execute(
                    insert_stmt,
                    {
                        "event_id": event_id,
                        "activity_type": activity_type,
                        "metadata": raw_log.raw_data,
                    }
                )

                # Log success
                session.add(
                    models.ActorProcessingLog(
                        actor_id=actor_id,
                        actor_version_at_processing=actor_version,
                        raw_log_id=raw_log.id,
                        event_id=event_id,
                        status=ProcessingStatus.SUCCESS,
                        details={"created_event_id": event_id},
                    )
                )

            await session.commit()
            logger.info(f"Created Event (id={event_id}) from RawLog (id={raw_log.id})")


# The extension loader will import this module, which will execute the
# @actor_registry.register decorators above, registering the actors.
logger.info("Example extension loaded successfully")

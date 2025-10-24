from typing import Any
import logging
from sqlmodel import select
from .. import models
from ..core.actors import ActorBase, ActorConfig, actor_registry
from ..db import async_session
from ..services import EmbeddingService
from ..services import EventService

logger = logging.getLogger(__name__)


@actor_registry.register(
    ActorConfig(
        slug="test-processor",
        actor_type=models.ActorType.PROCESSOR,
        version="1.0.0",
    )
)
class TestProcessor(ActorBase):
    """
    Example processor for 'test-source' data. Expects a 'message' field.
    """

    async def run(self, data: models.RawLog) -> Any:
        raw_log_input = data
        logger.info("Running 'test-processor' on raw_log_id: %s", raw_log_input.id)

        # Use a properly scoped async session context
        async with async_session() as session:
            # Ensure we use an instance attached to this session
            raw_log = await session.get(models.RawLog, raw_log_input.id)
            if not raw_log:
                logger.error("RawLog id=%s not found in DB.", raw_log_input.id)
                return

            # Look up the actor metadata (self) and event type
            stmt_actor = select(models.Actor).where(models.Actor.slug == "test-processor")
            actor = (await session.exec(stmt_actor)).one_or_none()
            if not actor or actor.id is None:
                logger.error("Could not find self in database. Aborting.")
                return
            actor_id = actor.id
            actor_version = actor.version

            event_type_slug = "test-event"  # This processor knows what it creates
            stmt_event_type = select(models.EventType).where(
                models.EventType.slug == event_type_slug
            )
            event_type = (await session.exec(stmt_event_type)).one_or_none()

            if not event_type:
                logger.error("EventType '%s' not found. Cannot process.", event_type_slug)
                # Log failure
                session.add(
                    models.ActorProcessingLog(
                        actor_id=actor_id,
                        actor_version_at_processing=actor_version,
                        raw_log_id=raw_log.id,
                        status="FAILURE",
                        details={"reason": "missing_event_type", "expected": event_type_slug},
                    )
                )
                await session.commit()
                return

            summary = raw_log.raw_data.get("message", "No message provided")
            if event_type.id is None:
                logger.error("EventType ID is None. Cannot create event.")
                return

            new_event = models.Event(
                processor_actor_id=actor_id,
                start_time=raw_log.ingested_at,
                event_type_id=event_type.id,
                summary=summary,
            )

            # Link the raw log and persist
            new_event.raw_logs.append(raw_log)
            session.add(new_event)

            # Flush to assign IDs, then supersede any prior events before commit
            await session.flush()
            event_id = new_event.id
            raw_log_id = raw_log.id

            superseded_event_ids: list[int] = []
            if event_id is not None and raw_log_id is not None:
                try:
                    superseded_event_ids = await EventService.supersede_prior_events_for_raw_log(
                        session,
                        processor_actor_id=actor_id,
                        raw_log_id=raw_log_id,
                        new_event_id=event_id,
                    )
                except Exception as e:
                    logger.warning(
                        "Superseding prior events failed for raw_log_id=%s new_event_id=%s: %s",
                        raw_log_id,
                        event_id,
                        e,
                    )

            # Commit creation and superseding atomically
            await session.commit()

            # Log success
            if event_id is not None:
                session.add(
                    models.ActorProcessingLog(
                        actor_id=actor_id,
                        actor_version_at_processing=actor_version,
                        raw_log_id=raw_log_id,
                        event_id=event_id,
                        status="SUCCESS",
                        details={
                            "created_event_id": event_id,
                            "superseded_event_ids": superseded_event_ids,
                        },
                    )
                )
                await session.commit()

            logger.info(
                "Created Event (id=%s) from RawLog (id=%s)", event_id, raw_log_id
            )

            # Create an embedding for the new event (if summary available)
            if event_id is not None:
                try:
                    await EmbeddingService.ensure_event_embedding(
                        session,
                        event_id=event_id,
                        actor_id=actor_id,
                    )
                except Exception as e:
                    logger.warning("Embedding generation failed for event_id=%s: %s", event_id, e)
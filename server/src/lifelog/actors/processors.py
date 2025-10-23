from typing import Any
from sqlmodel import select
from .. import models
from ..core.actors import ActorBase, ActorConfig, actor_registry
from ..db import async_session


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
        print(f"--- Running 'test-processor' on raw_log_id: {raw_log_input.id} ---")

        # Use a properly scoped async session context
        async with async_session() as session:
            # Ensure we use an instance attached to this session
            raw_log = await session.get(models.RawLog, raw_log_input.id)
            if not raw_log:
                print(f"ERROR: RawLog id={raw_log_input.id} not found in DB.")
                return

            # Look up the actor metadata (self) and event type
            stmt_actor = select(models.Actor).where(models.Actor.slug == "test-processor")
            actor = (await session.exec(stmt_actor)).one_or_none()
            if not actor or actor.id is None:
                print("ERROR: Could not find self in database. Aborting.")
                return
            actor_id = actor.id
            actor_version = actor.version

            event_type_slug = "test-event"  # This processor knows what it creates
            stmt_event_type = select(models.EventType).where(
                models.EventType.slug == event_type_slug
            )
            event_type = (await session.exec(stmt_event_type)).one_or_none()

            if not event_type:
                print(f"ERROR: EventType '{event_type_slug}' not found. Cannot process.")
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
                print("ERROR: EventType ID is None. Cannot create event.")
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

            # Flush to assign IDs, then cache for logging
            await session.flush()
            event_id = new_event.id
            raw_log_id = raw_log.id
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
                        details={"created_event_id": event_id},
                    )
                )
                await session.commit()

            print(
                f"SUCCESS: Created Event (id={event_id}) from RawLog (id={raw_log_id})"
            )